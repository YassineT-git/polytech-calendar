# Diagnostic et déploiement — 14 octobre 2026

## Ce qui est établi

Le run du 14 octobre à 07:57 (heure de Paris) échoue à « Générer tous les calendriers APP3 ». Checkout et installation Python réussissent ; la sauvegarde Git est sautée.

Run : https://github.com/YassineT-git/polytech-calendar/actions/runs/38519374721

L’API GitHub publique donne les étapes et annotations. Le téléchargement des logs complets répond HTTP 403 (« Must have admin rights to Repository »). Les annotations donnent seulement le code de sortie 1 ; l’avertissement Node.js 20 n’est pas la cause de l’étape Python en échec.

La version en ligne de `generate_ics.py` et de `update.yml` a été comparée aux fichiers joints : elles sont identiques au moment du diagnostic. Les calendriers générés dans l’archive sont anciens ; il ne faut pas recopier `docs/edt.ics` depuis cette archive sur le dépôt actuel.

Reproduction réelle avec le code original : `/api/weeks?category=app3` répond avec 104 semaines, mais chacune des requêtes `/api/timetable?category=app3&week=…` répond HTTP 502. Le script finit par `Impossible de récupérer le moindre emploi du temps.` La semaine actuelle (id 9, 12 octobre) répond elle aussi 502. Le code public du site PoPsEDT utilise exactement cette même API : aucune nouvelle URL vérifiée n’a été trouvée.

La panne actuelle se situe donc sur la récupération des données PoPsEDT, avant Git. Cela explique l’échec reproduit et est cohérent avec le run GitHub ; faute de logs complets, on ne peut pas certifier le détail de l’exception de chaque ancien run. Le 502 est renvoyé par l’infrastructure Cloudflare du service. La cause interne (hébergement, application ou ADE) n’est pas observable depuis ce projet.

## Corrections fournies

- Trois tentatives pour les erreurs réseau et HTTP 408/429/500/502/503/504, avec pauses de 2 puis 4 secondes. Les autres erreurs HTTP restent immédiates.
- Arrêt après trois semaines consécutives en erreur au lieu de solliciter les 104 semaines pendant une panne générale.
- Une seule semaine en échec annule la génération entière. Le code précédent acceptait certaines collectes partielles et pouvait supprimer les cours des semaines manquantes.
- Vérification de la structure des semaines et des réponses. Une réponse sans `courses` ou avec une erreur ne devient plus une semaine entreprise. Un `courses: []` valide garde le comportement existant.
- Calcul des 12 calendriers avant écriture, remplacement de chaque fichier par un fichier temporaire, maintien de l’alias INFO Groupe B et des URL.
- Tests hors réseau avant la collecte, message d’échec lisible et durée maximale du job.
- Actions checkout/setup-python v6 et Ubuntu 24.04 explicite pour retirer l’avertissement Node.js 20 et éviter une migration implicite du système.
- Publication explicite de `docs/` via les actions officielles GitHub Pages après réussite. Les commits d’un workflow utilisant `GITHUB_TOKEN` ne déclenchent pas une construction Pages depuis une branche : https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site . Le nouveau workflow suit https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages .

Les règles existantes de spécialité/groupe et de semaines entreprise sont conservées, y compris la semaine forcée du 19 octobre. La détection entreprise reste une heuristique : une vraie réponse vide est considérée comme telle ; on ne peut pas déduire une panne silencieuse du service à partir d’une liste vide valide.

## Installer les modifications

L’archive de correction contient seulement les fichiers à remplacer/ajouter, pas les anciens calendriers ni l’historique Git.

1. Télécharger et décompresser `polytech-calendar-correction.zip`.
2. Dans le dépôt GitHub actuel, remplacer `generate_ics.py`, `.github/workflows/update.yml`, `README.md`, puis ajouter `tests/test_generate_ics.py` et `DEPLOIEMENT.md`. Ne pas remplacer tout le dépôt par l’ancienne archive d’origine. Conserver `docs/` actuel.
3. Dans **Settings → Pages → Build and deployment → Source**, choisir **GitHub Actions**. Aucune création de workflow supplémentaire n’est nécessaire.
4. Enregistrer les cinq fichiers dans un même commit sur `main`. On peut aussi utiliser une branche et une pull request selon les habitudes du dépôt.
5. Dans **Actions → Mise à jour EDT Polytech APP3 → Run workflow**, lancer sur `main`.

Pour une copie locale du dépôt déjà à jour, le patch constitue une autre méthode :

```sh
git apply --check /chemin/polytech-calendar-correction.patch
git apply /chemin/polytech-calendar-correction.patch
python3 -m unittest discover -s tests -v
git diff --check
git add generate_ics.py .github/workflows/update.yml README.md tests/test_generate_ics.py DEPLOIEMENT.md
git commit -m "Fiabiliser la collecte PoPsEDT et publier les calendriers sur Pages"
git push origin main
```

Si `git apply --check` signale des conflits, ne pas forcer : comparer les fichiers actuels avec ceux de l’archive, en particulier les réglages personnels du générateur.

## Validation attendue

### Pendant la panne PoPsEDT

Le job reste rouge et `deploy` est sauté. Les nouvelles tentatives et le message « trois semaines consécutives en erreur » sont visibles. Aucun commit de calendriers n’est envoyé et aucun nouvel artefact Pages n’est publié. Le dernier calendrier publié reste accessible, mais son contenu peut être ancien. Un run vert pendant cette panne masquerait l’absence de nouvelles données.

### Quand le service répond à nouveau

- Les tests puis les étapes de génération, sauvegarde et publication réussissent.
- Les logs annoncent les 104 semaines collectées (ou le nombre actuellement proposé par le service), les 12 profils et le lien historique.
- Un nouveau commit de calendriers apparaît seulement si l’EDT a changé. Sans changement, la publication réussit quand même sans nouveau commit.
- Vérifier que `docs/edt.ics` et `docs/calendars/info-grb.ics` sont identiques.
- Vérifier la page https://YassineT-git.github.io/polytech-calendar/ et le calendrier https://YassineT-git.github.io/polytech-calendar/calendars/info-grb.ics . Pour un autre profil, utiliser son URL existante.
- Comparer le fichier servi par Pages avec celui de `main`, et contrôler un cours récent dont la date et la salle sont connues. Un HTTP 200 seul ne prouve pas que l’EDT est à jour.

Sur Mac, utiliser l’abonnement existant dans Calendrier et sélectionner **Présentation → Actualiser les calendriers**. Si le calendrier a été importé comme fichier local, créer un abonnement avec **Fichier → Nouvel abonnement à un calendrier**, coller l’URL ICS correspondant au profil et régler l’actualisation sur une heure. Vérifier ce même cours récent. L’alias historique `/edt.ics` reste utilisable pour INFO Groupe B.

Si les 502 persistent, le rétablissement demande une intervention du responsable de PoPsEDT / de sa source ADE, ou une URL de flux officiel accessible fournie par l’école. Aucune URL alternative ni données de remplacement ne sont inventées dans cette correction.

## Vérifications effectuées ici

- 11 tests réussis avec Python local : panne temporaire/persistante, HTTP 404, collecte partielle, réponses invalides, métadonnées invalides, semaine vide valide, arrêt anticipé, génération des 12 profils, alias, stabilité des fichiers, UTF-8/CRLF, horaires été/hiver et erreur avant écriture.
- YAML du workflow analysé avec succès ; dépendance `deploy → update` et permissions Pages vérifiées.
- Test réel du code corrigé : trois tentatives par semaine, arrêt après trois semaines toujours en 502, code de sortie 1 ; le fichier historique est identique octet pour octet à celui de l’archive d’origine.
- Le fonctionnement réseau en succès n’a pas pu être validé : PoPsEDT est encore en panne. La génération réussie a été testée avec des données de test dans un dossier temporaire.
- L’exécution complète sur Python 3.12 / Ubuntu et le déploiement Pages seront à confirmer dans GitHub Actions après installation. Aucun changement n’a été envoyé au dépôt distant dans cette session.
