# Catalogue de cours

Le launcher `cem_importer.py run` contient volontairement une liste prédéfinie des dépôts de cours connus du département d'informatique du CÉM.

Il n'est donc pas nécessaire de copier/coller des URLs GitHub ou de connaître le nom technique des dépôts. Le dossier créé dans Obsidian utilise le **code du cours et son nom humain**, puis le range dans un dossier de session.

| Session | Code | Dossier créé | Dépôt |
| --- | --- | --- | --- |
| 1 | `1P6` | `1P6 - Introduction à la programmation` | `departement-info-cem/1P6` |
| 2 | `2P6` | `2P6 - Programmation orientée objet` | `departement-info-cem/2P6` |
| 3 | `3W6` | `3W6 - Programmation Web transactionnelle` | `departement-info-cem/3W6-Web-Transactionelle` |
| 3 | `3S4` | `3S4 - Introduction à la cybersécurité` | `departement-info-cem/3s4-cybersec` |
| 3 | `3U4` | `3U4 - Introduction à la cybersécurité` | `departement-info-cem/3U4-cybersec` |
| 3 | `420-SN1` | `420-SN1 - Programmation en sciences` | `departement-info-cem/420-SN1` |
| 4 | `3M5` | `3M5 - Introduction à la programmation mobile` | `departement-info-cem/3M5-Intro-Mobile` |
| 4 | `4W6` | `4W6 - Programmation Web orientée services` | `departement-info-cem/4W6-WebServices` |
| 4 | `420-4A4` | `420-4A4 - Réseaux de neurones et sciences` | `departement-info-cem/420-4A4` |
| 5 | `4D5` | `4D5 - Base de données et programmation Web` | `departement-info-cem/4D5-Base-De-Donnees-Et-Prog-Web` |
| 5 | `5W5` | `5W5 - Programmation Web avancée` | `departement-info-cem/5W5-Web-Avancee` |
| 6 | `5N6` | `5N6 - Applications mobiles avancées` | `departement-info-cem/5N6-mobile-2` |
| — | `Z03` | `Z03 - Introduction à la programmation web` | `departement-info-cem/z03` |

`Z03` est un cours complémentaire et n'a donc pas une session fixe dans le cheminement; il est rangé dans `Autres cours`.

Les numéros de session sont gardés explicitement dans le catalogue. Cela évite de les déduire naïvement du premier chiffre du code : dans le cheminement DEC-BAC, par exemple, `3M5` se retrouve en session 4, `4D5` en session 5 et `5N6` en session 6.

Pour ajouter un nouveau dépôt officiel, ajoutez une entrée à `COURSES` dans `cem_importer.py`, avec sa session, puis ajoutez ou adaptez les tests de conversion si le cours introduit de nouveaux composants MDX.
