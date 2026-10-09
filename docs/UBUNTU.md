# Dell Power Manager sur Ubuntu

Ce document décrit l'installation, la vérification et le dépannage sur
Ubuntu, ainsi que ce qui a réellement été testé. Tout changement lié à
Ubuntu doit être consigné ici **et** dans `CHANGELOG.md`.

## Compatibilité

| Version Ubuntu | Statut | Détail |
|---|---|---|
| 24.04 LTS (noble) | **Supportée, testée** | libadwaita 1.5, GTK 4.14, Python 3.12 |
| 24.10 et plus récentes | Attendue compatible | dépendances plus récentes que le minimum ; non testée |
| 22.04 LTS (jammy) | **Non supportée** | libadwaita 1.1 : `Adw.AboutDialog` / `Adw.Dialog` (≥ 1.5) absents |

Minimum requis (déclaré dans `debian/control`) : `gir1.2-adw-1 (>= 1.5)`,
`gir1.2-gtk-4.0 (>= 4.10)`, `python3-gi`, `gir1.2-gudev-1.0`,
`gir1.2-gdkpixbuf-2.0`, `polkitd`, `dbus-daemon`.

Les saveurs (Kubuntu, Xubuntu, Ubuntu Budgie…) fonctionnent via
StatusNotifierItem ; Ubuntu Desktop (GNOME) l'affiche grâce à l'extension
`ubuntu-appindicators`, activée par défaut.

## Installation

Depuis un `.deb` pré-construit (dossier `packages/` ou page Releases) :

```bash
sudo apt install ./platform-power-manager_0.5.0-1_all.deb
```

`apt` installe automatiquement toutes les dépendances. Lancer ensuite
« Dell Power Manager » depuis le menu des applications, ou `platform-power`.
Le démon est activé à la demande par D-Bus (inutile de le démarrer à la
main) ; l'icône de la zone de notification démarre à l'ouverture de session
(`/etc/xdg/autostart/…`).

Construction depuis les sources :

```bash
sudo apt install build-essential debhelper dh-python devscripts fakeroot \
    gettext dbus python3-gi python3-pytest gir1.2-gtk-4.0 gir1.2-adw-1 \
    gir1.2-gudev-1.0 gir1.2-gdkpixbuf-2.0
dpkg-buildpackage -us -uc -b           # lance aussi les tests (nocheck pour les sauter)
sudo apt install ../platform-power-manager_*_all.deb
```

Désinstallation : `sudo apt remove platform-power-manager`.

## Vérifier le matériel (utilisateur normal, sans root)

```bash
cat /sys/firmware/acpi/platform_profile /sys/firmware/acpi/platform_profile_choices
ls /sys/class/power_supply/BAT0/ | grep charge_control
ls /sys/class/firmware-attributes/ 2>/dev/null
lsmod | grep -E 'dell_laptop|dell_wmi_sysman|dell_smbios'
```

- Rien dans `firmware-attributes` : le module `dell-wmi-sysman` n'est pas
  chargé pour ce modèle/BIOS ; l'onglet « BIOS avancé » le dira explicitement.
  Essayer `sudo modprobe dell-wmi-sysman` et lire `sudo dmesg | tail`.
- Les seuils de charge nécessitent le pilote `dell-laptop` (module du noyau
  Ubuntu standard).

## Particularités Ubuntu

- **power-profiles-daemon** (installé par défaut sur Ubuntu Desktop) pilote
  le même `platform_profile` que ce logiciel. Les deux restent cohérents car
  l'interface sysfs est unique ; le démon de ce projet surveille le fichier et
  met à jour la fenêtre et le tray si le profil est changé depuis GNOME
  (Paramètres → Alimentation).
- **Mots de passe polkit** : le changement de profil et de seuils est
  autorisé sans mot de passe pour l'utilisateur de la session locale active ;
  les réglages BIOS demandent l'authentification d'un administrateur (membre
  du groupe `sudo`).
- **AppArmor** (et non SELinux) : aucun profil n'est fourni ni nécessaire ;
  en cas de refus suspect, `sudo journalctl -k | grep -i apparmor`.
- **Pas de tray visible sur GNOME** : installer/activer l'extension
  (`sudo apt install gnome-shell-extension-appindicator`, puis
  `gnome-extensions enable ubuntu-appindicators@ubuntu.com` ou
  `gnome-extensions enable appindicatorsupport@rgcjonas.gmail.com`, puis
  fermer/rouvrir la session). Sans tray, fermer la fenêtre **quitte** l'application.
  Si l'extension est activée après le lancement, l'icône apparaît d'elle-même
  (depuis la 0.5.0).
- **Wayland** : sans incidence, l'application passe uniquement par D-Bus.
- **Noyaux récents (≥ 6.14)** : l'interface `/sys/firmware/acpi/platform_profile`
  est conservée par le noyau comme couche de compatibilité ; si un jour elle
  disparaissait, l'onglet thermique afficherait « non pris en charge ».

## Dépannage

```bash
systemctl status platform-power-daemon.service
journalctl -u platform-power-daemon.service -e
busctl --system introspect io.github.nplacide95.PlatformPower.Daemon1 \
    /io/github/nplacide95/PlatformPower/Daemon1
pkaction | grep platform-power          # 3 actions attendues
man platform-power
```

Menu ☰ → *Diagnostics* dans l'application : état D-Bus, `dell-wmi-sysman`,
verrouillage BIOS.

## Ce qui a été testé (0.5.0)

Environnement : conteneur Ubuntu 24.04.5 LTS, Python 3.12 système, GTK 4.14,
libadwaita 1.5.0, bus système `dbus-daemon` réel + `polkitd` réel (sans
systemd ni matériel Dell).

| Test | Résultat |
|---|---|
| Suite pytest (30 tests) sur l'interpréteur système, bus de session privé | OK |
| `dpkg-buildpackage -b` (tests exécutés pendant la construction) | OK |
| `lintian` sur le `.deb` | 0 erreur, 0 avertissement |
| `dpkg -i` du paquet ; politique polkit chargée (`pkaction` : 3 actions) | OK |
| Activation D-Bus du démon sur le bus système, `GetState` en utilisateur non privilégié | OK (état « non pris en charge », aucun matériel) |
| `SetPlatformProfile` depuis un utilisateur non privilégié | refusé par polkit (`AccessDenied`) comme attendu |
| `SetPlatformProfile` en root sans matériel | erreur propre « platform_profile is not exposed… » |
| Fenêtre GTK4 sous `xvfb`, démon joignable et injoignable | s'affiche, aucun message CRITICAL |
| Fermeture de la fenêtre sans hôte de tray | l'application quitte (code 0) |
| Enregistrement tardif du tray quand le `StatusNotifierWatcher` apparaît | OK (test simulé) |

**Non testé** (nécessite du matériel/une session réelle) : écriture effective
dans le sysfs d'un portable Dell (profils, seuils, attributs BIOS) sous
Ubuntu, rendu du tray dans GNOME Shell avec l'extension AppIndicator,
démarrage via systemd (`Type=dbus`, durcissement de l'unité). Ces points
reposent sur le code éprouvé sous Fedora et sur les mêmes interfaces noyau ;
à valider sur une vraie machine et à consigner ici (« Retours de tests »).

## Retours de tests sur matériel réel

*(à compléter : modèle, version d'Ubuntu, noyau, résultat)*
