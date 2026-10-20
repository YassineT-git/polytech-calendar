# Correction publiée — 20 octobre 2026

## Problèmes corrigés

Le seuil de 8 h et l'ancienne exception du 21 octobre créaient des plages entreprise pendant les cours. Le filtre de spécialité ignorait les suffixes ADE comme « APP3 PHOT TP », d'où des TP de photonique dans INFO, ELEC et MATE.

Le générateur reconnaît désormais les spécialités avec suffixes et respecte les couples spécialité/groupe. Les cours et leurs UID sont conservés. L'entreprise n'est plus déduite du nombre d'heures de cours.

## Calendrier officiel INFO Groupe B

Le PDF original `PPS_ING_PPS_IIM_catalogue_26_27.pdf`, retrouvé dans Téléchargements, a été rendu et inspecté à la page 7. Les rectangles colorés de la colonne année 1 ont été extraits avec leurs dates dans `data/alternance-info-2026-2027.json`. Son empreinte SHA256 est conservée. Les dates s'appliquent uniquement à INFO (IIM APP3), groupes A/B/C.

La transcription collée était erronée : les semaines du 14 septembre, du 12 octobre et du 19 octobre sont à l'école (cases vertes), pas en entreprise. La note des soutenances de première année, du 14 au 18 juin à l'école, est prioritaire sur les cellules jaunes du tableau pour ces dates.

Les jours entreprise sont uniquement les jours ouvrés jaunes hors jours fériés. Une fermeture de l'école n'est pas un congé personnel en entreprise. Les congés individuels restent à renseigner séparément. Les cours et réunions prennent la priorité sur leur créneau : l'entreprise peut être scindée sur un jour mixte, sans jamais chevaucher un événement école.

Les cours de la dernière collecte sont conservés à l'identique : 385 événements pour INFO Groupe B. La réparation rétablit 179 créneaux entreprise officiels, sans aucun chevauchement avec ces cours. Il ne s'agit pas d'une nouvelle récupération des cours depuis PoPsEDT.

## Publication

La source Pages est GitHub Actions. Le workflow « Publier les calendriers existants » publie les corrections commitées dans docs, indépendamment de PoPsEDT. « Mise à jour EDT Polytech APP3 » reste responsable de la collecte et signale une panne du fournisseur. Le 20 octobre, la liste des semaines répond, mais la semaine courante renvoie encore HTTP 502.

Les derniers fichiers restent disponibles même si la collecte échoue. Une publication réussie ne signifie donc pas que les cours ont été actualisés depuis ADE/PoPsEDT.

## Validation sur Mac

Actualiser l'abonnement existant via Présentation → Actualiser les calendriers. Ne pas créer un abonnement en double. L'URL INFO Groupe B et l'ancien `/edt.ics` sont conservés.

Vérifier la semaine du 19 octobre : cours, sans blocs entreprise. Vérifier le 1er octobre : entreprise le matin, réunion à l'école l'après-midi. Pour les groupes d'anglais et de TP numériques, il faut connaître les groupes exacts : ils ne sont pas déduits des groupes A/B/C.

## Maintenance

```sh
python3 -m unittest discover -s tests -v
python3 repair_calendars.py
```

Le nettoyage est idempotent et conserve les cours et UID du bon profil. L'extraction PDF est reproductible par `tools/extract_alternance_pdf.py` avec pdfplumber, mais nécessite un contrôle visuel pour toute nouvelle édition.
