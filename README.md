# Team Belote & Re

Application de gestion de tournois de belote **classique** et **coinchée**.
Backend Python (FastAPI + SQLAlchemy 2.0), interface web responsive installable
(PWA), synchronisation temps réel entre les tables.

*Nom de code du module : **Team Belote & Re** (paquet `tbr`).*

---

## 1. Principes de fonctionnement

| Élément | Règle |
|---|---|
| Effectif | multiple de 4, annoncé à la création du tournoi ; le tirage des tables en découle |
| Numéro de joueur | attribué à l'inscription (`dossard`), unique dans le tournoi |
| Tables | numérotées de 1 à N, recomposées à chaque manche |
| Manches | N manches de D donnes (10 par défaut, paramétrable de 1 à 30) |
| Saisie | le capitaine de table saisit chaque donne ; l'administrateur voit tout, corrige et clôture |
| Classement | cumul des points, départage par capots réussis, puis meilleure manche, puis capots subis |
| Capots | comptés par joueur (réussis / subis) et affichés sur la fiche individuelle |
| Confidentialité | pendant le tournoi un joueur ne voit que ses propres scores ; le classement complet est **publié à tous dès la clôture de la dernière manche** |
| Connexion | numéro de joueur + code PIN à 4 chiffres (Argon2id + JWT) |

Deux formats de tournoi, choisis à la création :

* **Mêlée tournante** — les joueurs changent de partenaire à chaque manche.
  L'appariement minimise les répétitions (partenaires puis adversaires) et peut
  suivre un **système suisse** (les joueurs de niveau proche se rencontrent) ou
  un **tirage aléatoire**.
* **Équipes fixes** — les paires restent soudées, seules les oppositions changent.
  Le classement individuel reste calculé, doublé d'un classement par équipe.

---

## 2. Règles de calcul

### Belote classique (`tbr/engine/classique.py`)

162 points par donne (152 de cartes + 10 de der).

* contrat réussi : chaque camp marque ses points ;
* **dedans** : le preneur marque 0, la défense 162 (la belote reste acquise au preneur) ;
* **litige** (81-81) : la défense marque 81, les 81 du preneur sont **reportés** sur
  la donne suivante au bénéfice du camp qui la remporte ;
* **capot** : 252 points (162 + 90) pour le camp qui réalise les huit plis ;
* belote / rebelote : 20 points, comptés dans la comparaison ;
* annonces de cartes (tierce 20 … carré de valets 200) activables par tournoi.

### Coinche (`tbr/engine/coinche.py`)

* contrats de 80 à 180 par pas de 10, **Capot 252**, **Générale 500** ;
* à la couleur (162 pts), **sans-atout** (130) ou **tout-atout** (258) — les points
  réalisés sont ramenés sur la base 162 pour être comparés au contrat ;
* **contrat réussi** : seul le preneur marque le montant du contrat (et ses
  éventuelles annonces / belote) ; la défense marque 0 ;
* **chute** : le preneur marque 0, sauf les 20 points de belote / rebelote
  annoncée ; la défense marque ses points de plis et ses éventuelles annonces ;
* après l'annonce du contrat, la défense peut **contrer** : tous les points
  attribués à la donne sont alors doublés (×2). Le preneur peut **surcontrer** :
  ils sont alors quadruplés (×4) ;
* capot et générale ne sont validés que si les huit plis sont effectivement faits.

Toutes ces valeurs sont regroupées dans `tbr/engine/rules.py` et surchargeables
par tournoi via le champ JSON `reglement` :

```json
{
  "variante": "CONTRAT_PLUS_REALISE",
  "litige_actif": true,
  "normaliser_sur_162": true,
  "departage_capots": true
}
```

---

## 3. Installation

### En local

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env          # définir TBR_SECRET_KEY (>= 32 caractères)
uvicorn tbr.main:app --reload --host 0.0.0.0 --port 8000
```

Interface : <http://localhost:8000> — API documentée : <http://localhost:8000/docs>

Au premier démarrage, un compte administrateur est créé à partir de
`TBR_ADMIN_NUMERO` / `TBR_ADMIN_PIN` (par défaut **numéro 1, PIN 1234** — à
changer immédiatement depuis l'onglet « Mon code »).

### Jeu de démonstration

```bash
python -m tbr.seed
```

16 joueurs, un tournoi de coinche en 3 manches, la première manche entièrement
saisie. Joueurs de démonstration : numéros 100 à 115, PIN = les 4 chiffres du
numéro (ex. `0100`).

### Conteneur

```bash
echo "TBR_SECRET_KEY=$(python -c 'import secrets;print(secrets.token_urlsafe(48))')" > .env
docker compose up --build
```

La base SQLite est persistée dans le volume `tbr-data`. Pour un déploiement en
ligne, remplacer `TBR_DATABASE_URL` par une URL PostgreSQL
(`postgresql+psycopg://…`) : aucun code n'est spécifique à SQLite.

### Tests

```bash
pytest          # 41 tests : moteur de règles, appariement, classement, API
```

---

## 3 bis. Mise en ligne — GitHub puis PythonAnywhere

### a. Publier le dépôt

```bash
cd team-belote-re
git init && git add . && git commit -m "Team Belote & Re - version initiale"
git branch -M main
git remote add origin https://github.com/<compte>/team-belote-re.git
git push -u origin main
```

Le workflow `.github/workflows/tests.yml` lance `pytest` à chaque push.
`.gitignore` exclut déjà `data/`, `.env` et les caches : **aucune base ni clé
secrète n'est poussée**.

### b. Déployer sur PythonAnywhere

1. **Console Bash** (onglet *Consoles*) :

   ```bash
   git clone https://github.com/<compte>/team-belote-re.git
   cd team-belote-re
   pip3.11 install --user -r requirements.txt
   python3.11 -c "import secrets; print(secrets.token_urlsafe(48))"   # notez la clé
   ```

2. **Onglet Web** → *Add a new web app* → *Manual configuration* → **Python 3.11**
   (3.11 minimum : le code utilise `StrEnum` et les annotations `X | None`).

3. **Fichier WSGI** (lien dans l'onglet Web) : remplacer tout le contenu par

   ```python
   import os, sys
   CHEMIN = "/home/<compte>/team-belote-re"
   sys.path.insert(0, CHEMIN)
   os.environ["TBR_SECRET_KEY"] = "<la clé générée à l'étape 1>"
   os.environ["TBR_DATABASE_URL"] = f"sqlite:///{CHEMIN}/data/tbr.db"
   os.environ["TBR_ADMIN_PIN"] = "<votre PIN admin initial>"
   from wsgi import application   # noqa: F401
   ```

4. **Fichiers statiques** (onglet Web, section *Static files*), pour décharger
   l'application : URL `/static/` → répertoire `/home/<compte>/team-belote-re/web/`.

5. **Reload**. L'application est en ligne sur
   `https://<compte>.pythonanywhere.com` en HTTPS, accessible depuis n'importe
   quel téléphone.

### b bis. Servir l'interface sur GitHub Pages

GitHub Pages ne peut héberger que l'interface statique : FastAPI, les comptes
et la base de données doivent rester sur PythonAnywhere. Après le déploiement
PythonAnywhere, renseignez son URL dans `web/runtime-config.js` :

```js
window.TBR_API_BASE = "https://<compte>.pythonanywhere.com";
```

Puis, à la racine du dépôt, exécutez `bash scripts/build_github_pages.sh` et
publiez les fichiers générés à la racine de la branche GitHub Pages. Les chemins
relatifs permettent alors à CSS, JavaScript, manifeste et icônes de fonctionner
sous `https://<compte-github>.github.io/<depot>/`.

### c. Mettre à jour ensuite

```bash
cd ~/team-belote-re && git pull && touch /var/www/<compte>_pythonanywhere_com_wsgi.py
```

### Ce qu'il faut savoir sur PythonAnywhere

* **Pas de WebSocket** : l'interface le détecte et bascule automatiquement sur une
  interrogation périodique (15 s, `PERIODE_SONDAGE` dans `web/app.js`). La
  synchronisation entre les tables reste assurée, avec quelques secondes de latence.
* **Un seul worker en offre gratuite** : SQLite convient parfaitement pour un
  club (quelques dizaines de joueurs). Au-delà, passer à MySQL en changeant
  simplement `TBR_DATABASE_URL`.
* **Sauvegarde** : `cp data/tbr.db data/tbr-$(date +%F).db` après chaque tournoi.
* L'offre gratuite met l'application en veille après trois mois d'inactivité :
  un simple *Run until 3 months from today* dans l'onglet Web la réactive.

---

## 4. Architecture

```
tbr/
├── engine/          moteur métier pur, sans dépendance à la base
│   ├── rules.py         enums, constantes, règlements paramétrables
│   ├── classique.py     calcul d'une donne de belote classique
│   ├── coinche.py       calcul d'une donne de coinche
│   ├── scoring.py       point d'entrée unique (saisie → score)
│   ├── pairing.py       composition des tables, anti-répétition
│   └── standings.py     classement individuel et par équipe
├── models.py        SQLAlchemy 2.0 (joueurs, tournois, manches, tables, donnes, audit)
├── services.py      orchestration : inscriptions, manches, saisie, classements
├── security.py      Argon2id + JWT
├── api/             routes FastAPI + hub WebSocket
├── main.py          application ASGI, sert aussi la PWA
└── seed.py          jeu de démonstration
web/                 PWA sans build : index.html, app.js, styles.css
tests/               pytest
```

Le moteur (`tbr/engine`) ne connaît ni la base ni HTTP : il se teste et se
réutilise seul. Toute la logique de règles y est isolée.

### Points d'API principaux

| Méthode | Route | Accès |
|---|---|---|
| POST | `/api/auth/login` | public |
| POST | `/api/tournaments` | administrateur |
| POST | `/api/tournaments/{id}/registrations` | administrateur |
| POST | `/api/tournaments/{id}/start` | administrateur |
| POST | `/api/tournaments/{id}/rounds` | administrateur (tire la manche suivante) |
| POST | `/api/tournaments/{id}/rounds/{n}/close` | administrateur |
| GET | `/api/tournaments/{id}/standings` | administrateur à tout moment ; **inscrits une fois le tournoi terminé** |
| GET | `/api/tournaments/{id}/standings/me` | joueur (sa ligne seule) |
| GET | `/api/tournaments/{id}/me/table` | joueur (sa table du moment) |
| POST | `/api/tables/{id}/deals` | capitaine de table ou administrateur |
| WS | `/ws/tournaments/{id}` | diffusion des donnes en direct |

Toute correction d'une donne déjà saisie est tracée dans `audit_logs`
(valeur avant / après, auteur, horodatage) et la table entière est recalculée
pour propager correctement les litiges.

---

## 5. Sécurité et exploitation

* Codes PIN hachés en Argon2id, jamais stockés en clair ; réinitialisation par
  l'administrateur depuis l'onglet « Joueurs ».
* `TBR_SECRET_KEY` doit être une valeur aléatoire d'au moins 32 caractères,
  propre à chaque installation : la changer invalide toutes les sessions.
* Le cloisonnement des scores est appliqué côté serveur, pas seulement dans
  l'interface : un joueur reçoit 403 sur le classement complet tant que le
  tournoi n'est pas terminé, ainsi que sur les manches et la liste des joueurs.
* Recommandation d'exploitation : servir derrière un reverse proxy HTTPS et
  restreindre `TBR_CORS_ORIGINS` au domaine du club.

---

## 6. Évolutions prévues sans refonte

* fin de manche à objectif de points (au lieu d'un nombre fixe de donnes) ;
* export PDF / tableur du classement et des feuilles de table ;
* mode hors-ligne complet avec file de synchronisation (le front est déjà
  découplé de l'API par une unique fonction `api()`) ;
* double validation d'une donne par le camp adverse (le modèle `Deal` prévoit
  déjà la traçabilité de l'auteur de la saisie).
