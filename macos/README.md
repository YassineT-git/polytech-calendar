# Synchronisation privée Polyflex → iCloud

Cette version conserve le calendrier personnel hors de GitHub et de GitHub Pages.
Le Mac collecte **Polyflex → Mon emploi du temps** et met à jour un calendrier iCloud
dédié. L'iPhone reçoit les événements via le même compte iCloud.

## Première activation

1. Construire ou ouvrir **Polytech Sync privé.app** sur le Mac.
2. Renseigner l'adresse et le mot de passe du compte Polyflex.
3. Choisir **Activer et synchroniser en privé** et accorder l'accès Calendrier demandé
   par macOS. L'accès complet est nécessaire pour retrouver, déplacer et retirer les
   événements précédemment synchronisés ; l'application utilise seulement le calendrier
   dédié qu'elle crée.
4. Attendre le message de réussite. Le calendrier **Polytech — EDT privé** doit apparaître
   sous iCloud dans Calendrier sur Mac et iPhone.
5. Masquer l'ancien abonnement collectif Polytech afin de ne plus afficher ses doublons.

Calendriers iCloud doit être activé sur les deux appareils. La collecte automatique
a lieu toutes les 30 minutes quand le Mac est allumé et connecté ; le Mac n'est pas
réveillé de force. L'iPhone conserve les derniers événements quand le Mac est éteint.
Les délais propres à iCloud s'ajoutent au temps de collecte.

L'activation copie l'application dans `~/Applications/Polytech Sync privé.app`,
enregistre les identifiants dans le trousseau local et installe son agent de lancement
`~/Library/LaunchAgents/fr.polytech.calendar.private.plist`. Le bouton
**Arrêter l'actualisation** désactive cet agent, sans effacer les événements iCloud.

## Données et règles

- Aucune publication de l'EDT personnel, de son statut ou de ses métadonnées sur GitHub.
- Aucun mot de passe dans le code, les fichiers de configuration ou les arguments de processus.
- Cookie de session temporaire ; formulaire et redirections vérifiés avant suivi.
- Le dossier local `~/Library/Application Support/PolytechCalendarPrivate` est privé
  au compte macOS. Il contient le dernier ICS, les révisions et le statut de synchronisation.
- Le calendrier iCloud est privé tant que l'utilisateur ne le partage pas lui-même.
- Les changements de cours conservent leur identité ; les séances retirées de Polyflex
  sont supprimées uniquement après une collecte complète valide.
- Les événements ajoutés manuellement sans marqueur de l'application sont conservés.
- Une panne Polyflex ne modifie aucun événement iCloud.
- Le planning d'entreprise repose sur la plaquette IIM année 1 ; horaires indicatifs
  9 h–17 h 30, hors week-ends/jours fériés. Les cours ont priorité sur leur créneau.
- Les congés personnels ne sont pas déduits. L'année suivante nécessite une nouvelle plaquette.

Les anciennes URL publiques collectives ne sont pas transformées en un calendrier
personnel. Leurs fichiers restent historiques et peuvent contenir des sous-groupes
qui ne correspondent pas au compte personnel.

## Construction et contrôles

Mac Apple Silicon, macOS 14 ou ultérieur. Python 3 doit être installé sur le Mac
(Homebrew, installation officielle ou outils Apple). Aucun paquet Python supplémentaire
n'est requis pour le collecteur.

```sh
python3 -m unittest discover -s tests -v
macos/build_private_app.sh /chemin/vers/le/dossier-de-sortie
"/chemin/vers/Polytech Sync privé.app/Contents/MacOS/PolytechPrivateSync" --validate-ics /chemin/vers/un-fichier-local.ics
```

L'autorisation macOS et une première synchronisation réelle restent nécessaires pour
valider le compte iCloud : un build réussi ne prouve pas que le compte est activé.
