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
- ne commit que si le contenu des calendriers a réellement changé.

## GitHub Pages

Configurer :

- Source : `Deploy from a branch`
- Branche : `main`
- Dossier : `/docs`

Le lien général est ensuite :

```text
https://TON-PSEUDO.github.io/polytech-calendar/
```
