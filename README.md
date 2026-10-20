# Polytech Calendar — APP3

Génère automatiquement des abonnements ICS pour les APP3 de Polytech Paris-Saclay à partir des données PoPsEDT.

## Profils générés

- Spécialités : ELEC, INFO, MATE, PHOT
- Groupes : GrA, GrB, GrC
- 12 calendriers dans `docs/calendars/`

La page GitHub Pages `docs/index.html` permet à chaque étudiant de choisir son profil et de récupérer le bon lien d'abonnement.

## Semaines entreprise

Une semaine vide ou contenant peu de cours n'est **pas** automatiquement une semaine entreprise : il peut s'agir de vacances ou d'un EDT non encore publié.

Les cours ont toujours la priorité. Dès qu'un cours du profil figure dans une semaine, aucun événement entreprise n'est ajouté dans cette semaine, même si elle avait été configurée comme entreprise.

Pour ajouter une semaine entreprise confirmée par le calendrier d'alternance, ajouter une date de cette semaine dans `generate_ics.py` :

```python
FORCED_ENTERPRISE_DATES = {
    # date(2026, 11, 2),  # Exemple uniquement : vérifier le calendrier officiel.
}
```

La liste est vide par défaut, en attendant les dates officielles. L'ancienne exception du 21 octobre 2026 a été retirée : elle forçait l'entreprise pendant une semaine contenant des cours. Les créneaux configurés restent du lundi au vendredi, de 09:00 à 17:30.

Les spécialités sont reconnues même avec un suffixe ADE (`APP3 PHOT TP`, par exemple). Les couples spécialité/groupe sont filtrés ensemble : INFO GrA + ELEC GrB n'autorise pas INFO GrB. Les groupes numériques de TP et les groupes d'anglais ne sont pas déduits des groupes A/B/C : ils restent inclus tant que le profil ne permet pas de les distinguer.

## Réparer les calendriers existants pendant une panne

```sh
python3 repair_calendars.py
```

Cette opération conserve à l'identique les événements et UID des cours du bon profil, retire les cours d'autres spécialités et les événements entreprise non confirmés ou incompatibles avec une semaine école. Elle ne récupère **aucun nouveau cours** et ne prétend pas actualiser l'EDT. L'alias INFO Groupe B est conservé.

Le workflow **Publier les calendriers existants** publie les corrections de `docs/` sur un push humain/authentifié ou sur déclenchement manuel, sans dépendre de PoPsEDT. Le workflow de collecte continue, lui, à signaler une panne du fournisseur et ne publie jamais une collecte partielle. Les deux publications sont sérialisées.

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
