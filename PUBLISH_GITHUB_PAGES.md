# Mise à jour GitHub Pages

Le site `https://atoutdunon-ship-it.github.io/Belote/` chargeait ses ressources sous `/static/`. Ce chemin n’existe pas dans GitHub Pages, où les fichiers du dépôt sont servis dans le sous-dossier `/Belote/`. Les styles et le script ne se chargeaient donc pas, ce qui expliquait l’affichage brut et l’absence de formulaire de connexion.

Le dossier `github-pages-repair` contient les fichiers à publier **à la racine de la branche `main` du dépôt `Belote`**. Dans GitHub, ouvrez le dépôt, choisissez **Add file → Upload files**, déposez le contenu extrait du dossier, cochez si nécessaire le remplacement des fichiers existants, puis validez le commit.

Les fichiers essentiels sont `index.html`, `styles.css`, `app.js`, `manifest.webmanifest`, `service-worker.js`, les icônes et le nouveau fichier `runtime-config.js`. Cette version comprend l’accès organisateur **Admin / Music7** et l’inscription autonome des joueurs avec leur numéro et leur PIN. Après la publication GitHub Pages, videz le cache du navigateur ou rechargez la page avec un rechargement forcé afin que le nouveau service worker remplace l’ancien.

> GitHub Pages héberge uniquement l’interface. Pour que les connexions, les joueurs et les tournois fonctionnent, renseignez ensuite l’adresse du serveur FastAPI déployé sur PythonAnywhere dans `runtime-config.js` : `window.TBR_API_BASE = "https://<votre-compte>.pythonanywhere.com";`.
