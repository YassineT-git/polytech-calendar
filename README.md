# Polytech Calendar — APP3

> **Synchronisation personnelle privée sur Mac et iPhone :** voir [la version locale iCloud](macos/README.md).
> Elle utilise l’EDT personnel Polyflex et garde les identifiants dans le trousseau du Mac.
> Le service public décrit ci-dessous reste le service collectif historique PoPsEDT.

Génère automatiquement des abonnements ICS pour les APP3 de Polytech Paris-Saclay à partir des données PoPsEDT.

## Profils générés

- Spécialités : ELEC, INFO, MATE, PHOT
- Groupes : GrA, GrB, GrC
- 12 calendriers dans `docs/calendars/`

La page GitHub Pages `docs/index.html` permet à chaque étudiant de choisir son profil et de récupérer le bon lien d'abonnement.

## Semaines entreprise

### INFO (IIM, première année / APP3)

Les dates proviennent des cellules colorées de la **colonne année 1**, page 7 du catalogue officiel `PPS_ING_PPS_IIM_catalogue_26_27.pdf`, fourni par l'utilisateur. Le fichier `data/alternance-info-2026-2027.json` conserve les dates, la page et l'empreinte SHA256 du PDF. Le calendrier IIM s'applique aux profils INFO A/B/C uniquement.

La transcription textuelle fournie était inexacte : les semaines du 14 septembre et des 12 et 19 octobre sont en école dans le PDF original. La note sur les soutenances du 14 au 18 juin à l'école est prioritaire sur les cellules jaunes de ces dates.

L'entreprise est ajoutée seulement aux jours ouvrés jaunes, hors jours fériés, de 09:00 à 17:30. Une fermeture de l'école ne signifie pas un congé de l'apprenti : les cellules jaunes restent en entreprise. Les congés personnels ne sont pas déduits.

Les cours et réunions sont conservés. Quand un événement école occupe une partie d'un jour entreprise, son créneau est retiré de l'entreprise : le 1er octobre, par exemple, l'entreprise s'arrête au début de la réunion. Il ne peut y avoir aucun chevauchement entreprise/cours. Les jours et semaines vertes ou roses ne reçoivent jamais d'entreprise automatique.

### Autres spécialités

Aucun calendrier d'alternance officiel n'a été fourni pour ELEC/MATE/PHOT. Une semaine vide ou contenant peu de cours n'est donc pas automatiquement une semaine entreprise. Ajouter une date confirmée dans `FORCED_ENTERPRISE_DATES` pour ces profils ; une semaine contenant des cours reste alors prioritaire. Les jours INFO sont indépendants de cette liste manuelle.

### Filtre des cours

Les spécialités sont reconnues même avec un suffixe ADE (`APP3 PHOT TP`, par exemple). Les couples spécialité/groupe sont filtrés ensemble : INFO GrA + ELEC GrB n'autorise pas INFO GrB. Les groupes numériques de TP et les groupes d'anglais ne sont pas déduits des groupes A/B/C : ils restent inclus tant que le profil ne permet pas de les distinguer.

## Réparer les calendriers existants pendant une panne

```sh
python3 repair_calendars.py
```

Cette opération conserve à l'identique les événements et UID des cours du bon profil, retire les cours d'autres spécialités et les anciens événements entreprise déduits du seuil de 8 h, puis rétablit les créneaux INFO selon le calendrier officiel sans chevauchement. Elle ne récupère **aucun nouveau cours** et ne prétend pas actualiser l'EDT. L'alias INFO Groupe B est conservé.

Le workflow **Publier les calendriers existants** publie les corrections de `docs/` sur un push humain/authentifié ou sur déclenchement manuel, sans dépendre de PoPsEDT. Le workflow de collecte continue, lui, à signaler une panne du fournisseur et ne publie jamais une collecte partielle. Les deux publications sont sérialisées.

Pour reproduire l'extraction du PDF (outil de maintenance, dépendance `pdfplumber`), après avoir contrôlé visuellement la page 7 :

```sh
python3 tools/extract_alternance_pdf.py /chemin/PPS_ING_PPS_IIM_catalogue_26_27.pdf data/alternance-info-2026-2027.json
python3 repair_calendars.py
python3 -m unittest discover -s tests -v
```

Les coordonnées de l'outil sont propres à cette édition. Ne pas l'utiliser pour un autre PDF sans vérifier les colonnes, couleurs, jours et notes.

## Ancien lien

`docs/edt.ics` est conservé et reste un alias du calendrier **INFO Groupe B** afin de ne pas casser les abonnements déjà installés.

## Ancienne automatisation publique (désactivée)

Le workflow `.github/workflows/update.yml` :

- n’est plus planifié automatiquement ;
- peut être lancé manuellement depuis l'onglet **Actions** ;
- vérifie le générateur avec les tests hors réseau ;
- ne commit que si le contenu des calendriers a réellement changé ;
- publie explicitement `docs/` sur GitHub Pages après une génération réussie.

Les erreurs réseau transitoires sont réessayées trois fois (pauses de 2 puis 4 secondes). Trois semaines consécutives en erreur interrompent la collecte. Une seule semaine manquante ou une réponse invalide annule toute la génération pour éviter la disparition de cours dans les abonnements. Un résultat explicite `courses: []` reste une semaine vide valide.

Une panne durable PoPsEDT reste un échec visible : les calendriers déjà publiés sont conservés, mais peuvent être anciens. Le workflow ne peut pas réparer le serveur distant.

## GitHub Pages

Configurer :

- Dans **Settings → Pages → Build and deployment → Source**, choisir **GitHub Actions**.
- Conserver le workflow fourni ; aucune création de workflow supplémentaire n’est nécessaire.
- Si une protection de branche interdit les commits du bot, autoriser ce workflow selon les règles du dépôt.

Ce réglage remplace `Deploy from a branch` : les commits effectués avec `GITHUB_TOKEN` ne déclenchent pas automatiquement la construction Pages. Le job `deploy` publie directement les fichiers générés. Les URL existantes restent les mêmes.

Le lien général est ensuite :

```text
https://YassineT-git.github.io/polytech-calendar/
```

## Tests et validation

```sh
python3 -m unittest discover -s tests -v
```

Voir `DEPLOIEMENT.md` pour le diagnostic, les instructions d’installation et les contrôles GitHub / Calendrier sur Mac.
