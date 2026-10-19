# Polytech Calendar — APP3

Génère automatiquement des abonnements ICS pour les APP3 de Polytech Paris-Saclay à partir des données PoPsEDT.

## Profils générés

- Spécialités : ELEC, INFO, MATE, PHOT
- Groupes : GrA, GrB, GrC
- 12 calendriers dans `docs/calendars/`

La page GitHub Pages `docs/index.html` permet à chaque étudiant de choisir son profil et de récupérer le bon lien d'abonnement.

## Semaines entreprise

Par défaut, une semaine contenant **au maximum 8 h de cours** pour un profil est considérée comme semaine entreprise. Des événements `🏢 Entreprise` sont ajoutés du lundi au vendredi de **09:00 à 17:30**, sans supprimer les éventuels petits événements Polytech de cette semaine.

Les réglages sont en haut de `generate_ics.py` :

```python
ENTERPRISE_MAX_SCHOOL_HOURS = 8.0
ENTERPRISE_START = time(9, 0)
ENTERPRISE_END = time(17, 30)
```

Pour forcer une semaine en entreprise, ajoute simplement une date située dans cette semaine :

```python
FORCED_ENTERPRISE_DATES = {
    date(2026, 10, 21),
}
```

Pour forcer une semaine en école malgré la détection automatique :

```python
FORCED_SCHOOL_DATES = {
    date(2026, 11, 9),
}
```

## Ancien lien

`docs/edt.ics` est conservé et reste un alias du calendrier **INFO Groupe B** afin de ne pas casser les abonnements déjà installés.

## Mise à jour automatique

Le workflow `.github/workflows/update.yml` :

- tourne toutes les 30 minutes ;
- peut être lancé manuellement depuis l'onglet **Actions** ;
- se lance aussi après une modification du générateur ou de la page d'accueil ;
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
