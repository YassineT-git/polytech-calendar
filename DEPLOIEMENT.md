# Correction des conflits — 20 octobre 2026

## Cause et changements

Le seuil de 8 h créait une semaine entreprise malgré des cours. Une exception forcée au 21 octobre ajoutait également l'entreprise pendant une semaine école. L'ancien filtre de spécialité ignorait `APP3 PHOT TP`, d'où des TP de photonique dans INFO, ELEC et MATE.

La nouvelle règle donne la priorité à tous les cours et n'ajoute l'entreprise que pour une semaine explicitement confirmée, sans cours. Aucun calendrier officiel d'alternance n'a encore été fourni : la liste entreprise est vide. Les anciens événements automatiques ont donc été retirés des 12 profils et du lien historique. Les cours du bon profil et leurs UID sont conservés ; seuls 4 événements de photonique par profil INFO/ELEC/MATE sont exclus.

## Publication

Configurer Settings → Pages → Source sur GitHub Actions. Le workflow « Publier les calendriers existants » publie les corrections déjà commitées dans docs, indépendamment d'une nouvelle collecte. Le workflow « Mise à jour EDT Polytech APP3 » reste responsable de la collecte, de ses erreurs et de sa publication lorsqu'elle réussit.

Le 20 octobre, la liste des semaines est accessible mais la semaine courante renvoie encore HTTP 502. Les nouveaux tests et le nettoyage ne rétablissent pas le serveur PoPsEDT. Les cours conservés peuvent donc être anciens. Les erreurs 5xx, y compris Cloudflare 530, sont désormais réessayées.

## Validation

```sh
python3 -m unittest discover -s tests -v
```

Après publication, actualiser l'abonnement Calendrier existant ; il est inutile d'ajouter un second abonnement. Vérifier que les blocs Entreprise ont disparu et que les cours sont toujours présents. INFO ne doit plus afficher les TP « Optique instrumentale » réservés à PHOT.

Quand PoPsEDT répond à nouveau, lancer manuellement « Mise à jour EDT Polytech APP3 ». Contrôler un cours récent avec l'EDT officiel ; une publication réussie des fichiers existants ne prouve pas la fraîcheur des cours.

Pour rétablir l'affichage Entreprise, renseigner FORCED_ENTERPRISE_DATES à partir du calendrier officiel. Les semaines comportant des cours resteront prioritaires. Pour les cours d'anglais et les sous-groupes de TP numériques, il faut connaître les groupes exacts de l'étudiant ; ils ne sont pas déduits des groupes A/B/C.
