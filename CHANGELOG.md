# Journal des modifications

Suivi complet du projet, version par version (le plus récent en premier).
Chaque changement, mineur ou majeur, doit être ajouté ici **dans le même
commit** que le code qu'il décrit. Format inspiré de
[Keep a Changelog](https://keepachangelog.com/fr/1.1.0/) ; le détail
spécifique à chaque format de paquet reste dans `debian/changelog`,
`platform-power-manager.spec` (`%changelog`) et
`packaging/opensuse/platform-power-manager.spec`.

Un test (`tests/test_packaging.py`) vérifie que la version annoncée ici est
identique à celle de `app.py`, `window.py`, du metainfo, des deux specs RPM
et de `debian/changelog`.

## [0.5.0] - 2026-10-09 — Intégration Ubuntu / Debian

Première version pensée pour Ubuntu (testée sur Ubuntu 24.04 LTS). Le
fonctionnement sur Fedora n'est pas modifié, hormis les deux correctifs du
tray/fenêtre ci-dessous qui profitent à toutes les distributions.

### Ajouté
- `docs/UBUNTU.md` : guide d'installation, de vérification matérielle, de
  dépannage (AppArmor, extension AppIndicator, `power-profiles-daemon`,
  modules noyau) et matrice de compatibilité Ubuntu.
- Page de manuel `platform-power(1)` dans le paquet Debian.
- Workflow GitHub Actions `.github/workflows/ci.yml` : tests sur Ubuntu 24.04
  (interpréteur système, GTK4/libadwaita réels, bus de session privé), lint
  des fichiers `.desktop`/metainfo, construction du `.deb` et passage de
  `lintian`.
- Tests : `tests/test_packaging.py` (cohérence des versions, XML valides,
  actions polkit déclarées = actions utilisées par le démon, catalogue
  français compilable, unité systemd Debian = lien vers l'unité partagée (vérifie qu'elle ne redevient pas une copie), politique D-Bus
  sous `/usr/share`) et `test_tray_registers_when_watcher_appears_late`.
- `tests/smoke_gui.py` : test de fumée de l'interface sous affichage virtuel
  (`xvfb-run`), avec ou sans démon joignable ; échoue sur tout message GLib
  CRITICAL et vérifie que la fermeture quitte sans tray.
- Le paquet Debian exécute désormais la suite pytest pendant la construction
  (`dh_auto_test`, ignorée avec `DEB_BUILD_OPTIONS=nocheck`).

- Workflow GitHub Actions `.github/workflows/release.yml` (déclenchement
  manuel) : construit le `.deb`, crée le tag `v<version>` et la release GitHub
  avec le `.deb` et son `.sha256` en pièces jointes.

### Modifié
- **Tray** : l'application s'enregistre auprès du `StatusNotifierWatcher` dès
  que son nom apparaît sur le bus (et se marque indisponible s'il disparaît).
  Avant, si l'autostart démarrait l'app avant que l'extension AppIndicator de
  GNOME (celle d'Ubuntu) ait pris le nom, l'icône n'apparaissait jamais
  jusqu'au prochain lancement ; idem après un redémarrage de GNOME Shell ou
  de Plasma.
- **Fenêtre** : fermer la fenêtre (croix, `Ctrl+W`, `Ctrl+Q`) **quitte
  réellement l'application quand aucun tray n'est disponible** (GNOME sans
  extension AppIndicator, sessions minimales). Avant, elle se cachait et
  laissait un processus invisible sans moyen de la rouvrir. Comportement
  inchangé (réduction dans le tray) quand un tray est présent.
- **Paquet Debian/Ubuntu** :
  - la politique D-Bus système est installée dans `/usr/share/dbus-1/system.d/`
    (et non plus `/etc/dbus-1/system.d/`, réservé à la configuration locale :
    avertissement lintian `dbus-policy-in-etc`) ;
  - dépendances explicites `gir1.2-adw-1 (>= 1.5)` et `gir1.2-gtk-4.0
    (>= 4.10)` (l'app utilise `Adw.AboutDialog`/`Adw.Dialog`) : Ubuntu 24.04
    LTS minimum, Ubuntu 22.04 n'est pas supporté ;
  - `${python3:Depends}` + `dh_python3` (compilation du bytecode gérée par le
    système de paquets) ;
  - `Suggests: gnome-shell-extension-appindicator` ;
  - le catalogue `fr.mo` est compilé dans `debian/` et non plus dans `po/`
    (l'arbre source reste propre) ;
  - `Homepage` pointe vers le dépôt GitHub réel (`ElMajor76/...`) ;
  - entrée de changelog datée distinctement (erreur lintian
    `latest-changelog-entry-without-new-date`).
- **Fenêtre** : suppression d'un `Adwaita-CRITICAL: adw_bin_set_child:
  assertion 'gtk_widget_get_parent (child) == NULL' failed` émis à chaque
  démarrage sous libadwaita 1.5 (Ubuntu 24.04) : la pile était réaffectée
  comme enfant du `Adw.Bin` qui la contenait déjà (`_show_content()`).
- Lanceur `.desktop` : catégories `Settings;HardwareSettings;` (retrait de
  `System`, deuxième catégorie principale : l'application pouvait apparaître
  en double dans le menu GNOME/Ubuntu ; signalé par `desktop-file-validate`).
- `.gitignore` : artefacts de construction Debian (`debian/.debhelper/`,
  `debian/files`, …), `.pytest_cache/`.
- Test existant `tests/test_tray.py` : la fixture restaure le vrai bus avant le
  nettoyage ; un test précédent laissait des objets D-Bus exportés qui
  faisaient échouer le test suivant.
- Version portée à 0.5.0 (`app.py`, `window.py`, metainfo, spec Fedora, spec
  openSUSE, `debian/changelog`, `PKGBUILD`).

- **Paquet Arch Linux** (`packaging/archlinux/PKGBUILD`) : version 0.5.0 ;
  politique D-Bus dans `/usr/share/dbus-1/system.d/` (plus de fichier `/etc`
  ni de `backup=`) ; page de manuel installée ; `optdepends`
  (`gnome-shell-extension-appindicator`, `power-profiles-daemon`) ; nouveau
  script `update-sha256.sh` qui calcule le checksum du tarball du tag.
  `check()` et `package()` ont été exécutés sur l'arbre du dépôt (29 tests OK,
  tous les fichiers installés présents, `ExecStart` réécrit vers
  `/usr/lib/platform-power-manager/`), mais **pas dans une vraie
  installation Arch** (miroirs Arch inaccessibles depuis l'environnement de
  développement) ; `makepkg` et `namcap` restent à lancer sur Arch.

### À faire / non traité
- `PKGBUILD` : `sha256sums=('SKIP')` tant que le tag `v0.5.0` n'existe pas.
  Après sa création : `cd packaging/archlinux && ./update-sha256.sh`, puis
  committer.
- Pas de test sur matériel Dell réel sous Ubuntu : la couche sysfs est testée
  en simulation et le démon a été validé sur un vrai bus système Ubuntu 24.04
  sans matériel (voir `docs/UBUNTU.md`, section « Ce qui a été testé »).

## [0.4.0] - 2026-09-27
### Modifié
- i18n : les chaînes de l'interface dans le code source sont en anglais ; le
  français est conservé comme traduction gettext complète (`po/fr.po`).
### Corrigé
- Trois titres de sections contenant un `&` brut (balisage Pango) n'étaient
  pas affichés ; reformulés avec « and »/« et ».
- La politique polkit n'avait pas de marqueurs `xml:lang` : ses actions
  s'affichaient toujours en français. Défauts anglais + surcharge `fr`.

## [0.3.0] - 2026-09-27
### Sécurité
- Durcissement de l'unité systemd (`PrivateTmp`, `RestrictAddressFamilies`,
  `RestrictNamespaces`, `LockPersonality`, `MemoryDenyWriteExecute`,
  `SystemCallFilter`).
- Documentation de la frontière de confiance de `sysfs.py`.
### Corrigé
- `set_charge_thresholds()` valide les bornes min/max du firmware avant
  d'écrire (plus de retour silencieux à l'ancienne valeur).
- `DaemonClient.watch_state_changed()` accepte plusieurs abonnés (le tray ne
  recevait plus rien une fois la fenêtre ouverte).
### Ajouté
- Tray : sous-menus profil thermique / mode de charge, coches mises à jour en
  direct (`ItemsPropertiesUpdated`), état de la batterie dans le menu.
- Fenêtre : menu principal (rafraîchir, diagnostics, raccourcis, documentation,
  signaler un problème, à propos).
- Premiers paquets Debian/Ubuntu, Arch Linux et openSUSE (commit `41f32d2`).

## [0.2.0] - 2026-09-22 (révisions -1 à -5 jusqu'au 2026-09-23)
### Sécurité
- Liste blanche/noire des attributs BIOS `dell-wmi-sysman` ; validation du nom
  de batterie et de l'identifiant d'attribut contre les listes découvertes
  (anti traversée de chemin) ; sujet polkit `system-bus-name`.
### Ajouté
- Modes de charge Dell natifs (Adaptive, Express, Standard, Primarily AC,
  Custom), surveillance temps réel (uevent GUdev + `Gio.FileMonitor`), client
  D-Bus asynchrone, autostart à l'ouverture de session (`--minimized`),
  catégories BIOS avancées réorganisées et traduites en français.
### Corrigé
- Icône du tray (`IconThemePath` vide, `IconPixmap`), icônes 16/22/24 px,
  icône symbolique de température.

## [0.1.0] - 2026-09-19 / 2026-09-20
- Version initiale (Fedora) : profil thermique ACPI, seuils de charge,
  attributs BIOS `dell-wmi-sysman` découverts dynamiquement, tray
  StatusNotifierItem, renommage « Dell Power Manager », RPM pré-construit.
