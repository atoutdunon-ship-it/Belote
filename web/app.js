/* Team Belote & Re — interface unique administrateur / capitaine / joueur. */
'use strict';

/* Filet de sécurité : une erreur imprévue ne doit jamais laisser une page
   blanche sans explication. Enregistré avant toute autre instruction. */
window.addEventListener('error', (evt) => {
  const cible = document.getElementById('vue');
  if (cible && !cible.innerHTML.trim()) {
    cible.innerHTML = '<div class="message erreur">Impossible de démarrer l\'interface : '
      + String((evt && evt.message) || 'erreur inconnue')
      + '. Rechargez la page ; si le problème persiste, ouvrez l\'application '
      + 'dans un onglet plein écran plutôt que dans un cadre intégré.</div>';
  }
});

/* Le stockage local est indisponible ou lève une exception dans certains
   contextes (navigation privée, cookies tiers bloqués, iframe cloisonnée).
   L'application doit fonctionner sans, la session étant alors non persistante. */
const stock = {
  lire(cle) { try { return localStorage.getItem(cle); } catch (e) { return null; } },
  ecrire(cle, valeur) { try { localStorage.setItem(cle, valeur); } catch (e) { /* sans effet */ } },
  effacer(cle) { try { localStorage.removeItem(cle); } catch (e) { /* sans effet */ } },
};

const TOTAUX = { ATOUT: 162, SANS_ATOUT: 130, TOUT_ATOUT: 258 };
const CONTRATS = [80, 90, 100, 110, 120, 130, 140, 150, 160, 170, 180, 252, 500];
const API_BASE = String(window.TBR_API_BASE || '').replace(/\/+$/, '');
const ANNONCES = [
  ['TIERCE', 'Tierce 20'],
  ['CINQUANTE', 'Cinquante 50'],
  ['CENT', 'Cent 100'],
  ['CARRE_SIMPLE', 'Carré 100'],
  ['CARRE_NEUFS', 'Carré de 9 — 150'],
  ['CARRE_VALETS', 'Carré de valets — 200'],
];

const S = {
  token: stock.lire('tbr_token'),
  moi: null,
  vue: 'connexion',
  tournois: [],
  tournoiId: Number(stock.lire('tbr_tournoi')) || null,
  tournoi: null,
  inscrits: [],
  manches: [],
  classement: null,
  maTable: null,
  mesResultats: null,
  joueurs: [],
  message: null,
  ws: null,
  sondage: null,
};

const $ = (sel) => document.querySelector(sel);
const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

/* ------------------------------------------------------------------ API */

async function api(chemin, options = {}) {
  const entetes = { 'Content-Type': 'application/json', ...(options.headers || {}) };
  if (S.token) entetes.Authorization = `Bearer ${S.token}`;
  const reponse = await fetch(`${API_BASE}/api${chemin}`, { ...options, headers: entetes });
  if (reponse.status === 401) { deconnexion(); throw new Error('Session expirée.'); }
  if (reponse.status === 204) return null;
  const corps = await reponse.json().catch(() => null);
  if (!reponse.ok) {
    const detail = corps && corps.detail;
    throw new Error(typeof detail === 'string' ? detail : 'Requête refusée.');
  }
  return corps;
}

function signaler(texte, type = 'erreur') {
  S.message = texte ? { texte, type } : null;
  rendre();
}

/* ------------------------------------------------------- Authentification */

async function connexion(payload) {
  const data = await api('/auth/login', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
  S.token = data.access_token;
  stock.ecrire('tbr_token', S.token);
  S.moi = data;
  S.vue = data.is_admin ? 'tournois' : 'rejoindre';
  await charger();
}

function deconnexion() {
  S.token = null; S.moi = null; S.vue = 'connexion'; S.tournoiId = null; S.tournoi = null;
  stock.effacer('tbr_token');
  stock.effacer('tbr_tournoi');
  if (S.ws) { S.ws.close(); S.ws = null; }
  if (S.sondage) { clearInterval(S.sondage); S.sondage = null; }
  rendre();
}

/* ------------------------------------------------------------ Chargement */

async function charger() {
  try {
    if (!S.moi) {
      const moi = await api('/auth/me');
      S.moi = { player_id: moi.id, numero: moi.numero, nom: moi.nom, is_admin: moi.is_admin };
      if (S.vue === 'connexion') S.vue = moi.is_admin ? 'tournois' : 'rejoindre';
    }
    S.tournois = await api('/tournaments');
    if (!S.tournoiId && S.tournois.length) S.tournoiId = S.tournois[0].id;
    if (S.tournoiId) {
      stock.ecrire('tbr_tournoi', String(S.tournoiId));
      S.tournoi = S.tournois.find((t) => t.id === S.tournoiId) || null;
      if (S.tournoi) await chargerTournoi();
    }
    S.message = null;
  } catch (err) {
    S.message = { texte: err.message, type: 'erreur' };
  }
  rendre();
  brancherFlux();
}

async function chargerTournoi() {
  const id = S.tournoiId;
  if (S.moi.is_admin) {
    if (S.vue === 'inscriptions') S.inscrits = await api(`/tournaments/${id}/registrations`);
    if (S.vue === 'manche') S.manches = await api(`/tournaments/${id}/rounds`);
    if (S.vue === 'classement') S.classement = await api(`/tournaments/${id}/standings`);
    if (S.vue === 'joueurs') S.joueurs = await api('/players');
  } else {
    if (S.vue === 'ma-table') {
      S.maTable = await api(`/tournaments/${id}/me/table`).catch(() => null);
    }
    if (S.vue === 'mes-resultats' || S.vue === 'suivi') {
      S.mesResultats = await api(`/tournaments/${id}/standings/me`).catch(() => null);
      if (S.vue === 'suivi') S.maTable = await api(`/tournaments/${id}/me/table`).catch(() => null);
    }
    if (S.vue === 'classement') {
      S.classement = await api(`/tournaments/${id}/standings`).catch(() => null);
    }
  }
}

async function rafraichir() {
  try { await chargerTournoi(); S.message = null; }
  catch (err) { S.message = { texte: err.message, type: 'erreur' }; }
  rendre();
}

/* Temps reel : WebSocket quand l'hebergeur le permet, sinon interrogation
   periodique (PythonAnywhere et la plupart des mutualises ne routent pas le WS). */
const PERIODE_SONDAGE = 15000;

function brancherFlux() {
  if (!S.tournoiId || !S.token) return;
  demarrerSondage();
  if (S.ws && S.ws.tournoi === S.tournoiId && S.ws.readyState <= 1) return;
  if (S.ws) { try { S.ws.close(); } catch (e) { /* ignore */ } }
  S.ws = null;
  try {
    const endpoint = new URL(API_BASE || location.origin);
    endpoint.protocol = endpoint.protocol === 'https:' ? 'wss:' : 'ws:';
    endpoint.pathname = `${endpoint.pathname.replace(/\/$/, '')}/ws/tournaments/${S.tournoiId}`;
    const ws = new WebSocket(endpoint.toString());
    ws.tournoi = S.tournoiId;
    ws.onmessage = () => rafraichir();
    ws.onerror = () => { /* l'interrogation periodique prend le relais */ };
    ws.onclose = () => { if (S.ws === ws) S.ws = null; };
    S.ws = ws;
  } catch (e) { S.ws = null; }
}

function demarrerSondage() {
  if (S.sondage) return;
  S.sondage = setInterval(() => {
    if (!S.token || !S.tournoiId) return;
    if (document.hidden) return;
    if (S.ws && S.ws.readyState === 1) return; // le WebSocket suffit
    if (document.activeElement && ['INPUT', 'SELECT'].includes(document.activeElement.tagName)) return;
    rafraichir();
  }, PERIODE_SONDAGE);
}

/* ----------------------------------------------------------- Navigation */

const ONGLETS_ADMIN = [
  ['tournois', 'Tournois'],
  ['inscriptions', 'Inscriptions'],
  ['manche', 'Manche en cours'],
  ['classement', 'Classement'],
  ['joueurs', 'Joueurs'],
  ['compte', 'Mon code'],
];
const ONGLETS_JOUEUR = [
  ['rejoindre', 'Rejoindre un tournoi'],
  ['ma-table', 'Ma table'],
  ['mes-resultats', 'Mes résultats'],
  ['suivi', 'Suivi du tournoi'],
  ['classement', 'Classement final'],
  ['compte', 'Mon code'],
];

async function aller(vue) {
  S.vue = vue;
  fermerTiroir();
  await rafraichir();
}

function ouvrirTiroir() {
  $('#tiroir').classList.add('ouvert');
  $('#voile').classList.add('ouvert');
  document.body.classList.add('verrou');
  $('#btn-menu').setAttribute('aria-expanded', 'true');
}
function fermerTiroir() {
  $('#tiroir').classList.remove('ouvert');
  $('#voile').classList.remove('ouvert');
  document.body.classList.remove('verrou');
  $('#btn-menu').setAttribute('aria-expanded', 'false');
}

/* --------------------------------------------------------------- Rendu */

function rendre() {
  const connecte = Boolean(S.moi);
  $('#tiroir').hidden = !connecte;
  $('#btn-quitter').hidden = !connecte;
  $('#identite').hidden = !connecte;
  $('#btn-menu').style.visibility = connecte ? 'visible' : 'hidden';

  if (connecte) {
    $('#identite').textContent = `${S.moi.nom} — n°${S.moi.numero}${S.moi.is_admin ? ' — admin' : ''}`;
    $('#contexte').textContent = S.tournoi
      ? `${S.tournoi.nom} — ${S.tournoi.game_type === 'COINCHE' ? 'Coinche' : 'Classique'}`
      : 'Aucun tournoi sélectionné';
    const onglets = S.moi.is_admin ? ONGLETS_ADMIN : ONGLETS_JOUEUR;
    $('#nav').innerHTML =
      `<div class="etiquette bleu nav-identite">${esc(S.moi.nom)} — n°${S.moi.numero}</div>` +
      onglets
      .map(([cle, libelle]) =>
        `<button data-vue="${cle}" class="${S.vue === cle ? 'actif' : ''}">${libelle}</button>`)
      .join('');
  } else {
    $('#contexte').textContent = 'Gestion de tournois';
    $('#nav').innerHTML = '';
  }

  const alerte = S.message
    ? `<div class="message ${S.message.type}">${esc(S.message.texte)}</div>` : '';
  $('#vue').innerHTML = alerte + vueCourante();
  brancher();
}

function vueCourante() {
  if (!S.moi) return vueConnexion();
  switch (S.vue) {
    case 'tournois': return vueTournois();
    case 'inscriptions': return vueInscriptions();
    case 'manche': return vueManche();
    case 'classement': return vueClassement();
    case 'joueurs': return vueJoueurs();
    case 'rejoindre': return vueRejoindre();
    case 'ma-table': return vueMaTable();
    case 'mes-resultats': return vueMesResultats();
    case 'suivi': return vueSuivi();
    case 'compte': return vueCompte();
    default: return '<div class="carte"><p>Vue inconnue.</p></div>';
  }
}

function vueConnexion() {
  const configurationManquante = location.hostname.endsWith('github.io') && !API_BASE;
  return `
  <section class="carte connexion">
    <h1>Connexion</h1>
    <p>Les joueurs utilisent leur numéro et leur code PIN. L'organisateur utilise son identifiant et son mot de passe.</p>
    ${configurationManquante ? '<div class="message info">L’interface GitHub Pages est prête, mais le serveur de scores n’est pas encore configuré. Ajoutez son adresse PythonAnywhere dans <code>runtime-config.js</code> pour activer la connexion.</div>' : ''}
    <form id="form-connexion" class="grille">
      <h2>Espace joueur</h2>
      <div><label for="numero">Numéro de joueur</label>
        <input id="numero" name="numero" type="number" inputmode="numeric" required autocomplete="username"></div>
      <div><label for="pin">Code PIN à 4 chiffres</label>
        <input id="pin" name="pin" type="password" inputmode="numeric" maxlength="4" required autocomplete="current-password"></div>
      <button class="action" type="submit">Se connecter comme joueur</button>
    </form>
    <hr class="separateur">
    <form id="form-connexion-admin" class="grille">
      <h2>Espace organisateur</h2>
      <div><label for="identifiant-admin">Identifiant</label>
        <input id="identifiant-admin" name="identifiant" type="text" required autocomplete="username"></div>
      <div><label for="mot-de-passe-admin">Mot de passe</label>
        <input id="mot-de-passe-admin" name="mot_de_passe" type="password" required autocomplete="current-password"></div>
      <button class="action discret" type="submit">Se connecter comme organisateur</button>
    </form>
  </section>`;
}

function vueRejoindre() {
  const t = S.tournoi;
  if (!t) return '<section class="carte"><h1>Rejoindre un tournoi</h1><p>Aucun tournoi n’est actuellement ouvert aux inscriptions.</p></section>';
  const ouvert = t.statut === 'BROUILLON';
  const inscrit = Boolean(t.est_inscrit);
  return selecteurTournoi() + `
  <section class="carte connexion">
    <h1>Rejoindre un tournoi</h1>
    <h2>${esc(t.nom)}</h2>
    <p>${t.inscrits} inscrit(s) sur ${t.nb_joueurs} places. ${t.game_type === 'COINCHE' ? 'Belote coinchée.' : 'Belote classique.'}</p>
    ${inscrit
      ? '<div class="message succes">Vous êtes inscrit à ce tournoi. Votre table sera affichée lorsque l’organisateur lancera la première manche.</div>'
      : ouvert
        ? '<button class="action" id="btn-rejoindre">Rejoindre ce tournoi</button>'
        : '<div class="message info">Les inscriptions à ce tournoi sont closes.</div>'}
  </section>`;
}

function selecteurTournoi() {
  if (!S.tournois.length) return '';
  return `
  <div class="carte">
    <label for="sel-tournoi">Tournoi actif</label>
    <select id="sel-tournoi">
      ${S.tournois.map((t) => `<option value="${t.id}" ${t.id === S.tournoiId ? 'selected' : ''}>
        ${esc(t.nom)} — ${esc(t.statut)}</option>`).join('')}
    </select>
  </div>`;
}

function vueTournois() {
  const lignes = S.tournois.map((t) => `
    <tr>
      <td>${esc(t.nom)}</td>
      <td>${t.game_type === 'COINCHE' ? 'Coinche' : 'Classique'}</td>
      <td>${t.format === 'MELEE' ? 'Mêlée' : 'Équipes fixes'}</td>
      <td class="chiffre">${t.inscrits}/${t.nb_joueurs}</td>
      <td class="chiffre">${t.manches_jouees}/${t.nb_manches}</td>
      <td><span class="etiquette ${t.statut === 'EN_COURS' ? 'bleu' : ''}">${esc(t.statut)}</span></td>
      <td><button class="action discret" data-choisir="${t.id}">Ouvrir</button></td>
    </tr>`).join('');

  return `
  <section class="carte">
    <h1>Créer un tournoi</h1>
    <form id="form-tournoi" class="grille trois">
      <div><label for="t-nom">Nom du tournoi</label><input id="t-nom" required value="Tournoi du club"></div>
      <div><label for="t-jeu">Type de belote</label>
        <select id="t-jeu"><option value="CLASSIQUE">Belote classique</option><option value="COINCHE">Belote coinchée</option></select></div>
      <div><label for="t-format">Format</label>
        <select id="t-format"><option value="MELEE">Mêlée tournante</option><option value="EQUIPES_FIXES">Équipes fixes</option></select></div>
      <div><label for="t-methode">Appariement</label>
        <select id="t-methode"><option value="SUISSE">Système suisse (par niveau)</option><option value="ALEATOIRE">Tirage aléatoire</option></select></div>
      <div><label for="t-joueurs">Nombre de participants (multiple de 4)</label>
        <input id="t-joueurs" type="number" step="4" min="4" value="16" required></div>
      <div><label for="t-manches">Nombre de manches</label>
        <input id="t-manches" type="number" min="1" max="20" value="3" required></div>
      <div><label for="t-donnes">Donnes par manche</label>
        <input id="t-donnes" type="number" min="1" max="30" value="10" required></div>
      <div><label for="t-annonces">Annonces de cartes</label>
        <select id="t-annonces"><option value="0">Désactivées</option><option value="1">Activées</option></select></div>
      <div style="display:flex;align-items:flex-end"><button class="action" type="submit">Créer le tournoi</button></div>
    </form>
  </section>

  <section class="carte">
    <h2>Tournois</h2>
    <div class="tableau-enveloppe">
      <table>
        <thead><tr><th>Nom</th><th>Jeu</th><th>Format</th><th class="chiffre">Inscrits</th>
          <th class="chiffre">Manches</th><th>Statut</th><th></th></tr></thead>
        <tbody>${lignes || '<tr><td colspan="7">Aucun tournoi.</td></tr>'}</tbody>
      </table>
    </div>
  </section>`;
}

function vueInscriptions() {
  if (!S.tournoi) return selecteurTournoi() + '<div class="carte"><p>Créez un tournoi pour commencer.</p></div>';
  const t = S.tournoi;
  const lignes = S.inscrits.map((i) => `
    <tr>
      <td class="chiffre">${i.dossard}</td>
      <td>${esc(i.nom)}</td>
      <td class="chiffre">${i.numero}</td>
      <td>${i.team_nom ? esc(i.team_nom) : '—'}</td>
      <td>${t.statut === 'BROUILLON'
        ? `<button class="action discret" data-retirer="${i.id}">Retirer</button>` : ''}</td>
    </tr>`).join('');

  return selecteurTournoi() + `
  <section class="carte">
    <h1>Inscriptions — ${esc(t.nom)}</h1>
    <p>${S.inscrits.length} inscrit(s) sur ${t.nb_joueurs} annoncés.
       ${t.format === 'EQUIPES_FIXES' ? 'Les joueurs sont regroupés deux par deux en équipes.' : ''}</p>
    ${t.statut === 'BROUILLON' ? `
    <form id="form-inscription" class="rangee">
      <div><label for="i-nom">Nom du joueur (créé si inconnu)</label><input id="i-nom" placeholder="Prénom Nom"></div>
      <div><label for="i-numero">ou numéro d'un joueur existant</label><input id="i-numero" type="number" inputmode="numeric"></div>
      <div><label for="i-dossard">Numéro dans le tournoi</label><input id="i-dossard" type="number" inputmode="numeric" placeholder="auto"></div>
      <button class="action" type="submit">Inscrire</button>
    </form>` : '<p>Le tournoi a démarré : les inscriptions sont closes.</p>'}
    <div class="tableau-enveloppe">
      <table>
        <thead><tr><th class="chiffre">N° tournoi</th><th>Joueur</th><th class="chiffre">N° licence</th><th>Équipe</th><th></th></tr></thead>
        <tbody>${lignes || '<tr><td colspan="5">Aucun inscrit.</td></tr>'}</tbody>
      </table>
    </div>
    ${t.statut === 'BROUILLON' ? `
      <div style="margin-top:14px"><button class="action" id="btn-demarrer"
        ${S.inscrits.length === t.nb_joueurs ? '' : 'disabled'}>Lancer le tournoi et tirer la manche 1</button></div>` : ''}
  </section>`;
}

function vueManche() {
  if (!S.tournoi) return selecteurTournoi() + '<div class="carte"><p>Aucun tournoi.</p></div>';
  const t = S.tournoi;
  if (!S.manches.length) {
    return selecteurTournoi() +
      '<div class="carte"><p>Le tournoi n\'a pas encore démarré. Lancez-le depuis l\'onglet Inscriptions.</p></div>';
  }
  const manche = S.manches[S.manches.length - 1];
  const complete = manche.tables.every((tb) => tb.donnes.length >= t.donnes_par_manche);

  return selecteurTournoi() + `
  <section class="carte">
    <div class="rangee">
      <h1 style="flex:1 1 auto">Manche ${manche.index} / ${t.nb_manches}
        <span class="etiquette ${manche.statut === 'EN_COURS' ? 'bleu' : 'vert'}">${esc(manche.statut)}</span></h1>
      ${manche.statut === 'EN_COURS'
        ? `<button class="action" id="btn-cloturer" ${complete ? '' : 'disabled'}>Clôturer la manche</button>`
        : (manche.index < t.nb_manches
            ? '<button class="action" id="btn-manche-suivante">Tirer la manche suivante</button>'
            : '<span class="etiquette vert">Tournoi terminé</span>')}
    </div>
    <p>${t.donnes_par_manche} donnes par table. ${complete ? 'Toutes les tables ont terminé.' : 'Saisie en cours.'}</p>
  </section>
  <div class="grille tables">
    ${manche.tables.map((tb) => carteTable(tb, manche, true)).join('')}
  </div>`;
}

function carteTable(tb, manche, admin) {
  const donnes = tb.donnes.map((d) => `
    <tr>
      <td class="chiffre">${d.index}</td>
      <td class="chiffre">${d.score_ns}</td>
      <td class="chiffre">${d.score_ew}</td>
      <td>${esc(libelleIssue(d))}</td>
      ${admin ? `<td><button class="action discret" data-suppr-donne="${tb.id}:${d.index}">Suppr.</button></td>` : ''}
    </tr>`).join('');
  const prochain = tb.donnes.length + 1;
  const saisieOuverte = manche.statut === 'EN_COURS' && prochain <= tb.donnes_attendues;

  return `
  <div class="table-jeu">
    <header>
      <h2 style="margin:0">Table ${tb.numero}</h2>
      <span class="etiquette">${tb.donnes.length}/${tb.donnes_attendues} donnes</span>
    </header>
    <div class="grille deux">
      <div class="camp"><div class="noms">${tb.ns.map((j) => esc(j.nom)).join(' &amp; ')}</div>
        <div class="score">${tb.total_ns}</div></div>
      <div class="camp"><div class="noms">${tb.ew.map((j) => esc(j.nom)).join(' &amp; ')}</div>
        <div class="score">${tb.total_ew}</div></div>
    </div>
    ${tb.donnes.length ? `<div class="tableau-enveloppe" style="margin-top:12px">
      <table><thead><tr><th class="chiffre">Donne</th><th class="chiffre">Camp 1</th>
        <th class="chiffre">Camp 2</th><th>Issue</th>${admin ? '<th></th>' : ''}</tr></thead>
      <tbody>${donnes}</tbody></table></div>` : ''}
    ${saisieOuverte ? formulaireDonne(tb, prochain) : ''}
  </div>`;
}

function libelleIssue(d) {
  const detail = d.detail || {};
  const issues = {
    CONTRAT_REUSSI: 'Contrat réussi', DEDANS: 'Dedans', LITIGE: 'Litige',
    CHUTE: 'Chute', CAPOT_PRENEUR: 'Capot du preneur', CAPOT_DEFENSE: 'Capot de la défense',
  };
  const base = issues[detail.issue] || '';
  const preneur = detail.preneur === 'NS' ? 'camp 1' : 'camp 2';
  const contrat = detail.contrat ? ` ${detail.contrat}` : '';
  const mult = detail.multiplicateur === 2 ? ' contré' : detail.multiplicateur === 4 ? ' surcontré' : '';
  return `${base} — ${preneur}${contrat}${mult}`;
}

function formulaireDonne(tb, index) {
  const coinche = S.tournoi.game_type === 'COINCHE';
  const annonces = S.tournoi.annonces_actives;
  const nomNS = tb.ns.map((j) => j.nom).join(' & ');
  const nomEW = tb.ew.map((j) => j.nom).join(' & ');
  const options = (v1, v2) => `<option value="NS">${esc(v1)}</option><option value="EW">${esc(v2)}</option>`;

  return `
  <form class="grille deux form-donne" data-table="${tb.id}" style="margin-top:14px">
    <h3 style="grid-column:1/-1">Donne n° ${index}</h3>
    <div><label>Preneur</label><select name="taker">${options(nomNS, nomEW)}</select></div>
    <div><label>Atout</label><select name="trump">
      <option value="ATOUT">À la couleur (162)</option>
      <option value="SANS_ATOUT">Sans-atout (130)</option>
      <option value="TOUT_ATOUT">Tout-atout (258)</option></select></div>
    ${coinche ? `
    <div><label>Contrat annoncé</label><select name="contract">
      ${CONTRATS.map((c) => `<option value="${c}" ${c === 100 ? 'selected' : ''}>${
        c === 252 ? 'Capot 252' : c === 500 ? 'Générale 500' : c}</option>`).join('')}</select></div>
    <div><label>Statut du contrat</label><select name="multiplier">
      <option value="1">Simple (×1)</option><option value="2">Contré par la défense (×2)</option><option value="4">Surcontré par le preneur (×4)</option></select></div>` : ''}
    <div><label>Points ${esc(nomNS)}</label>
      <input name="points_ns" type="number" inputmode="numeric" min="0" value="0" required></div>
    <div><label>Points ${esc(nomEW)}</label>
      <input name="points_ew" type="number" inputmode="numeric" min="0" value="162" required></div>
    <div><label>Belote / rebelote (+20 points)</label><select name="belote">
      <option value="">Aucune</option>${options(nomNS, nomEW)}</select></div>
    <div><label>Capot</label><select name="capot">
      <option value="">Aucun</option>${options(nomNS, nomEW)}</select></div>
    ${annonces ? `
    <fieldset style="grid-column:1/-1;border:1px solid var(--bordure);border-radius:10px">
      <legend><h3 style="margin:0">Annonces</h3></legend>
      <div class="grille deux">
        <div><label>${esc(nomNS)}</label>${ANNONCES.map(([k, l]) =>
          `<label style="font-weight:500;color:var(--texte)"><input type="checkbox" style="width:auto;min-height:auto;margin-right:8px" name="ann_ns" value="${k}">${l}</label>`).join('')}</div>
        <div><label>${esc(nomEW)}</label>${ANNONCES.map(([k, l]) =>
          `<label style="font-weight:500;color:var(--texte)"><input type="checkbox" style="width:auto;min-height:auto;margin-right:8px" name="ann_ew" value="${k}">${l}</label>`).join('')}</div>
      </div>
    </fieldset>` : ''}
    <input type="hidden" name="index" value="${index}">
    <div style="grid-column:1/-1"><button class="action" type="submit">Enregistrer la donne ${index}</button></div>
  </form>`;
}

function vueSuivi() {
  const sel = S.tournois.length > 1 ? selecteurTournoi() : '';
  const t = S.tournoi;
  if (!t) return sel + '<div class="carte"><h1>Suivi du tournoi</h1><p>Aucun tournoi.</p></div>';
  const c = S.mesResultats ? S.mesResultats.classement : null;
  const tb = S.maTable;
  const statuts = { BROUILLON: 'Inscriptions en cours', EN_COURS: 'En cours', TERMINE: 'Terminé' };

  return sel + `
  <section class="carte">
    <h1>${esc(t.nom)}</h1>
    <p>${t.game_type === 'COINCHE' ? 'Belote coinchée' : 'Belote classique'} —
       ${t.format === 'MELEE' ? 'mêlée tournante' : 'équipes fixes'} —
       <span class="etiquette ${t.statut === 'TERMINE' ? 'vert' : 'bleu'}">${esc(statuts[t.statut] || t.statut)}</span></p>
    <div class="grille trois">
      <div class="stat"><div class="titre">Manche</div><div class="valeur">${t.manches_jouees}<span style="font-size:1rem"> / ${t.nb_manches}</span></div></div>
      <div class="stat"><div class="titre">Donnes par manche</div><div class="valeur">${t.donnes_par_manche}</div></div>
      <div class="stat"><div class="titre">Participants</div><div class="valeur">${t.inscrits}</div></div>
      <div class="stat"><div class="titre">Ma table</div><div class="valeur">${tb ? tb.numero : '—'}</div></div>
      <div class="stat"><div class="titre">Mon total</div><div class="valeur">${c ? c.total : 0}</div></div>
      <div class="stat"><div class="titre">Mon rang</div><div class="valeur">${c ? c.rank : '—'}<span style="font-size:1rem">${c ? ' / ' + c.participants : ''}</span></div></div>
    </div>
  </section>
  ${tb ? `
  <section class="carte">
    <h2>Ma table en cours — table ${tb.numero}, manche ${tb.manche}</h2>
    <div class="grille deux">
      <div class="camp"><div class="noms">${tb.ns.map((j) => esc(j.nom)).join(' &amp; ')}</div>
        <div class="score">${tb.total_ns}</div></div>
      <div class="camp"><div class="noms">${tb.ew.map((j) => esc(j.nom)).join(' &amp; ')}</div>
        <div class="score">${tb.total_ew}</div></div>
    </div>
    <p style="margin-top:10px">${tb.donnes.length} donne(s) saisie(s) sur ${tb.donnes_attendues}.</p>
  </section>` : ''}
  <section class="carte">
    <h2>Classement</h2>
    <p>${t.statut === 'TERMINE'
      ? 'Le tournoi est terminé : le classement complet est consultable dans l\'onglet « Classement final ».'
      : 'Pendant le tournoi, vous ne voyez que vos propres scores. Le classement complet de tous les participants sera publié dès la clôture de la dernière manche.'}</p>
  </section>`;
}

function vueClassement() {
  if (!S.classement) {
    const attente = S.moi && !S.moi.is_admin
      ? 'Le classement complet sera publié dès la clôture de la dernière manche. '
        + 'En attendant, retrouvez vos points dans « Mes résultats ».'
      : 'Aucun classement disponible.';
    return selecteurTournoi() + `<div class="carte"><h1>Classement</h1><p>${attente}</p></div>`;
  }
  const { tournoi, joueurs, equipes } = S.classement;
  const manches = Array.from({ length: tournoi.manches_jouees }, (_, i) => i + 1);
  const lignes = joueurs.map((j) => `
    <tr>
      <td class="chiffre">${j.rank}</td>
      <td class="chiffre">${j.dossard ?? '—'}</td>
      <td>${esc(j.nom)}</td>
      ${manches.map((m) => `<td class="chiffre">${j.per_round[m] ?? 0}</td>`).join('')}
      <td class="chiffre"><strong>${j.total}</strong></td>
      <td class="chiffre">${j.capots_reussis}</td>
      <td class="chiffre">${j.capots_subis}</td>
    </tr>`).join('');

  const tableauEquipes = equipes ? `
  <section class="carte">
    <h2>Classement par équipe</h2>
    <div class="tableau-enveloppe"><table>
      <thead><tr><th class="chiffre">Rang</th><th>Équipe</th><th>Joueurs</th>
        <th class="chiffre">Total</th><th class="chiffre">Capots</th></tr></thead>
      <tbody>${equipes.map((e) => `<tr><td class="chiffre">${e.rank}</td><td>${esc(e.nom)}</td>
        <td>${e.joueurs.map(esc).join(' & ')}</td><td class="chiffre"><strong>${e.total}</strong></td>
        <td class="chiffre">${e.capots_reussis}</td></tr>`).join('')}</tbody>
    </table></div>
  </section>` : '';

  return selecteurTournoi() + `
  <section class="carte">
    <h1>Classement général</h1>
    <div class="grille trois" style="margin-bottom:14px">
      <div class="stat"><div class="titre">Participants</div><div class="valeur">${tournoi.inscrits}</div></div>
      <div class="stat"><div class="titre">Manches jouées</div><div class="valeur">${tournoi.manches_jouees}/${tournoi.nb_manches}</div></div>
      <div class="stat"><div class="titre">Donnes par manche</div><div class="valeur">${tournoi.donnes_par_manche}</div></div>
    </div>
    <div class="tableau-enveloppe"><table>
      <thead><tr><th class="chiffre">Rang</th><th class="chiffre">N°</th><th>Joueur</th>
        ${manches.map((m) => `<th class="chiffre">M${m}</th>`).join('')}
        <th class="chiffre">Total</th><th class="chiffre">Capots +</th><th class="chiffre">Capots −</th></tr></thead>
      <tbody>${lignes}</tbody>
    </table></div>
  </section>
  ${tableauEquipes}`;
}

function vueJoueurs() {
  const lignes = S.joueurs.map((j) => `
    <tr>
      <td class="chiffre">${j.numero}</td>
      <td>${esc(j.nom)}</td>
      <td>${j.is_admin ? '<span class="etiquette bleu">Administrateur</span>' : 'Joueur'}</td>
      <td>${j.actif ? 'Actif' : 'Inactif'}</td>
      <td><button class="action discret" data-pin="${j.id}">Réinitialiser le code</button></td>
    </tr>`).join('');
  return `
  <section class="carte">
    <h1>Joueurs</h1>
    <form id="form-joueur" class="rangee">
      <div><label for="j-nom">Nom</label><input id="j-nom" required placeholder="Prénom Nom"></div>
      <div><label for="j-numero">Numéro (auto si vide)</label><input id="j-numero" type="number" inputmode="numeric"></div>
      <div><label for="j-pin">Code PIN initial</label><input id="j-pin" maxlength="4" value="0000"></div>
      <div><label for="j-admin">Rôle</label><select id="j-admin"><option value="0">Joueur</option><option value="1">Administrateur</option></select></div>
      <button class="action" type="submit">Ajouter</button>
    </form>
    <div class="tableau-enveloppe"><table>
      <thead><tr><th class="chiffre">Numéro</th><th>Nom</th><th>Rôle</th><th>Statut</th><th></th></tr></thead>
      <tbody>${lignes || '<tr><td colspan="5">Aucun joueur.</td></tr>'}</tbody>
    </table></div>
  </section>`;
}

function vueMaTable() {
  const sel = S.tournois.length > 1 ? selecteurTournoi() : '';
  if (!S.maTable) {
    return sel + '<div class="carte"><h1>Ma table</h1><p>Aucune manche en cours pour vous. ' +
      'Le tirage des tables est fait par l\'organisateur.</p></div>';
  }
  const tb = S.maTable;
  const manche = { index: tb.manche, statut: 'EN_COURS' };
  const monCamp = tb.mon_camp === 'NS' ? 'camp 1' : 'camp 2';
  return sel + `
  <section class="carte">
    <h1>Manche ${tb.manche} — table ${tb.numero}</h1>
    <p>Vous jouez dans le ${monCamp}.
      ${tb.est_capitaine ? 'Vous êtes capitaine de table : c\'est vous qui saisissez les donnes.'
        : 'La saisie est assurée par le capitaine de la table.'}</p>
  </section>
  ${tb.est_capitaine ? carteTable(tb, manche, false)
    : carteTable({ ...tb, donnes_attendues: -1 }, { ...manche, statut: 'CLOTUREE' }, false)}`;
}

function vueMesResultats() {
  const sel = S.tournois.length > 1 ? selecteurTournoi() : '';
  if (!S.mesResultats) return sel + '<div class="carte"><h1>Mes résultats</h1><p>Aucun résultat disponible.</p></div>';
  const { classement: c, detail, tournoi } = S.mesResultats;
  const manches = Object.keys(c.per_round).map(Number).sort((a, b) => a - b);
  return sel + `
  <section class="carte">
    <h1>Mes résultats — ${esc(tournoi.nom)}</h1>
    <div class="grille trois">
      <div class="stat"><div class="titre">Classement</div><div class="valeur">${c.rank}<span style="font-size:1rem"> / ${c.participants}</span></div></div>
      <div class="stat"><div class="titre">Total de points</div><div class="valeur">${c.total}</div></div>
      <div class="stat"><div class="titre">Capots réussis</div><div class="valeur">${c.capots_reussis}</div></div>
      <div class="stat"><div class="titre">Capots subis</div><div class="valeur">${c.capots_subis}</div></div>
      <div class="stat"><div class="titre">Meilleure manche</div><div class="valeur">${c.meilleure_manche}</div></div>
      <div class="stat"><div class="titre">Donnes jouées</div><div class="valeur">${c.donnes_jouees}</div></div>
    </div>
  </section>
  <section class="carte">
    <h2>Détail par manche</h2>
    <div class="tableau-enveloppe"><table>
      <thead><tr><th class="chiffre">Manche</th><th class="chiffre">Table</th>
        <th class="chiffre">Mes points</th><th class="chiffre">Points adverses</th></tr></thead>
      <tbody>${detail.map((d) => `<tr><td class="chiffre">${d.manche}</td><td class="chiffre">${d.table}</td>
        <td class="chiffre"><strong>${d.total}</strong></td>
        <td class="chiffre">${d.donnes.reduce((s, x) => s + x.points_adverses, 0)}</td></tr>`).join('')
        || '<tr><td colspan="4">Aucune donne jouée.</td></tr>'}</tbody>
    </table></div>
    <p style="margin-top:10px">Total cumulé sur ${manches.length} manche(s).</p>
  </section>`;
}

function vueCompte() {
  if (S.moi && S.moi.is_admin) {
    return `
    <section class="carte connexion">
      <h1>Changer le mot de passe administrateur</h1>
      <form id="form-password-admin" class="grille">
        <div><label for="a-ancien">Mot de passe actuel</label><input id="a-ancien" type="password" required autocomplete="current-password"></div>
        <div><label for="a-nouveau">Nouveau mot de passe (6 caractères minimum)</label><input id="a-nouveau" type="password" required autocomplete="new-password"></div>
        <button class="action" type="submit">Enregistrer</button>
      </form>
    </section>`;
  }
  return `
  <section class="carte connexion">
    <h1>Changer mon code PIN</h1>
    <form id="form-pin" class="grille">
      <div><label for="p-ancien">Code actuel</label><input id="p-ancien" type="password" maxlength="4" required></div>
      <div><label for="p-nouveau">Nouveau code (4 chiffres)</label><input id="p-nouveau" type="password" maxlength="4" required></div>
      <button class="action" type="submit">Enregistrer</button>
    </form>
  </section>`;
}

/* ------------------------------------------------------------ Handlers */

function brancher() {
  document.querySelectorAll('#nav button').forEach((b) =>
    b.addEventListener('click', () => aller(b.dataset.vue)));

  const sel = $('#sel-tournoi');
  if (sel) sel.addEventListener('change', async () => {
    S.tournoiId = Number(sel.value);
    stock.ecrire('tbr_tournoi', sel.value);
    S.tournoi = S.tournois.find((t) => t.id === S.tournoiId) || null;
    brancherFlux();
    await rafraichir();
  });

  const fc = $('#form-connexion');
  if (fc) fc.addEventListener('submit', async (e) => {
    e.preventDefault();
    try { await connexion({ numero: Number($('#numero').value), pin: String($('#pin').value) }); }
    catch (err) { signaler(err.message); }
  });

  const fca = $('#form-connexion-admin');
  if (fca) fca.addEventListener('submit', async (e) => {
    e.preventDefault();
    try {
      await connexion({
        identifiant: $('#identifiant-admin').value.trim(),
        mot_de_passe: $('#mot-de-passe-admin').value,
      });
    } catch (err) { signaler(err.message); }
  });

  const ft = $('#form-tournoi');
  if (ft) ft.addEventListener('submit', async (e) => {
    e.preventDefault();
    try {
      const cree = await api('/tournaments', {
        method: 'POST',
        body: JSON.stringify({
          nom: $('#t-nom').value,
          game_type: $('#t-jeu').value,
          format: $('#t-format').value,
          pairing_method: $('#t-methode').value,
          nb_joueurs: Number($('#t-joueurs').value),
          nb_manches: Number($('#t-manches').value),
          donnes_par_manche: Number($('#t-donnes').value),
          annonces_actives: $('#t-annonces').value === '1',
        }),
      });
      S.tournoiId = cree.id;
      S.vue = 'inscriptions';
      await charger();
    } catch (err) { signaler(err.message); }
  });

  const br = $('#btn-rejoindre');
  if (br) br.addEventListener('click', async () => {
    try {
      await api(`/tournaments/${S.tournoiId}/join`, { method: 'POST' });
      await charger();
      signaler('Inscription enregistrée. Votre dossard a été attribué.', 'succes');
    } catch (err) { signaler(err.message); }
  });

  document.querySelectorAll('[data-choisir]').forEach((b) =>
    b.addEventListener('click', async () => {
      S.tournoiId = Number(b.dataset.choisir);
      S.vue = 'inscriptions';
      await charger();
    }));

  const fi = $('#form-inscription');
  if (fi) fi.addEventListener('submit', async (e) => {
    e.preventDefault();
    const corps = {};
    if ($('#i-numero').value) corps.numero = Number($('#i-numero').value);
    if ($('#i-nom').value.trim()) corps.nom = $('#i-nom').value.trim();
    if ($('#i-dossard').value) corps.dossard = Number($('#i-dossard').value);
    try {
      await api(`/tournaments/${S.tournoiId}/registrations`, { method: 'POST', body: JSON.stringify(corps) });
      await charger();
    } catch (err) { signaler(err.message); }
  });

  document.querySelectorAll('[data-retirer]').forEach((b) =>
    b.addEventListener('click', async () => {
      try {
        await api(`/tournaments/${S.tournoiId}/registrations/${b.dataset.retirer}`, { method: 'DELETE' });
        await charger();
      } catch (err) { signaler(err.message); }
    }));

  const bd = $('#btn-demarrer');
  if (bd) bd.addEventListener('click', async () => {
    try {
      await api(`/tournaments/${S.tournoiId}/start`, { method: 'POST' });
      S.vue = 'manche';
      await charger();
    } catch (err) { signaler(err.message); }
  });

  const bc = $('#btn-cloturer');
  if (bc) bc.addEventListener('click', async () => {
    const m = S.manches[S.manches.length - 1];
    try {
      await api(`/tournaments/${S.tournoiId}/rounds/${m.index}/close`, { method: 'POST' });
      await charger();
    } catch (err) { signaler(err.message); }
  });

  const bs = $('#btn-manche-suivante');
  if (bs) bs.addEventListener('click', async () => {
    try {
      await api(`/tournaments/${S.tournoiId}/rounds`, { method: 'POST' });
      await charger();
    } catch (err) { signaler(err.message); }
  });

  document.querySelectorAll('[data-suppr-donne]').forEach((b) =>
    b.addEventListener('click', async () => {
      const [tableId, index] = b.dataset.supprDonne.split(':');
      try {
        await api(`/tables/${tableId}/deals/${index}`, { method: 'DELETE' });
        await rafraichir();
      } catch (err) { signaler(err.message); }
    }));

  document.querySelectorAll('.form-donne').forEach(brancherFormulaireDonne);

  const fj = $('#form-joueur');
  if (fj) fj.addEventListener('submit', async (e) => {
    e.preventDefault();
    try {
      await api('/players', {
        method: 'POST',
        body: JSON.stringify({
          nom: $('#j-nom').value.trim(),
          numero: $('#j-numero').value ? Number($('#j-numero').value) : null,
          pin: $('#j-pin').value || '0000',
          is_admin: $('#j-admin').value === '1',
        }),
      });
      await rafraichir();
    } catch (err) { signaler(err.message); }
  });

  document.querySelectorAll('[data-pin]').forEach((b) =>
    b.addEventListener('click', async () => {
      const pin = prompt('Nouveau code PIN à 4 chiffres :', '0000');
      if (!pin) return;
      try {
        await api(`/players/${b.dataset.pin}/pin`, { method: 'POST', body: JSON.stringify({ pin }) });
        signaler('Code PIN réinitialisé.', 'succes');
      } catch (err) { signaler(err.message); }
    }));

  const fp = $('#form-pin');
  if (fp) fp.addEventListener('submit', async (e) => {
    e.preventDefault();
    try {
      await api('/auth/pin', {
        method: 'POST',
        body: JSON.stringify({ ancien_pin: $('#p-ancien').value, nouveau_pin: $('#p-nouveau').value }),
      });
      signaler('Code PIN mis à jour.', 'succes');
    } catch (err) { signaler(err.message); }
  });

  const fpa = $('#form-password-admin');
  if (fpa) fpa.addEventListener('submit', async (e) => {
    e.preventDefault();
    try {
      await api('/auth/password', {
        method: 'POST',
        body: JSON.stringify({
          ancien_mot_de_passe: $('#a-ancien').value,
          nouveau_mot_de_passe: $('#a-nouveau').value,
        }),
      });
      signaler('Mot de passe administrateur mis à jour.', 'succes');
    } catch (err) { signaler(err.message); }
  });
}

function brancherFormulaireDonne(form) {
  const total = () => TOTAUX[form.trump.value] || 162;
  const ns = form.points_ns;
  const ew = form.points_ew;

  const synchro = (source) => {
    const t = total();
    const v = Math.max(0, Math.min(t, Number(source.value) || 0));
    source.value = String(v);
    (source === ns ? ew : ns).value = String(t - v);
  };
  ns.addEventListener('input', () => synchro(ns));
  ew.addEventListener('input', () => synchro(ew));
  form.trump.addEventListener('change', () => synchro(ns));
  form.capot.addEventListener('change', () => {
    const t = total();
    if (form.capot.value === 'NS') { ns.value = String(t); ew.value = '0'; }
    else if (form.capot.value === 'EW') { ns.value = '0'; ew.value = String(t); }
  });

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const cases = (nom) => Array.from(form.querySelectorAll(`input[name="${nom}"]:checked`)).map((c) => c.value);
    const corps = {
      index: Number(form.index.value),
      taker: form.taker.value,
      trump: form.trump.value,
      points_ns: Number(ns.value),
      points_ew: Number(ew.value),
      belote: form.belote.value || null,
      capot: form.capot.value || null,
      generale: form.contract ? Number(form.contract.value) === 500 : false,
      declarations_ns: cases('ann_ns'),
      declarations_ew: cases('ann_ew'),
    };
    if (form.contract) {
      corps.contract = Number(form.contract.value);
      corps.multiplier = Number(form.multiplier.value);
    }
    try {
      await api(`/tables/${form.dataset.table}/deals`, { method: 'POST', body: JSON.stringify(corps) });
      await rafraichir();
    } catch (err) { signaler(err.message); }
  });
}

/* ------------------------------------------------------------ Amorçage */

$('#btn-menu').addEventListener('click', () =>
  $('#tiroir').classList.contains('ouvert') ? fermerTiroir() : ouvrirTiroir());
$('#voile').addEventListener('click', fermerTiroir);
$('#btn-quitter').addEventListener('click', deconnexion);
document.addEventListener('keydown', (e) => { if (e.key === 'Escape') fermerTiroir(); });

if ('serviceWorker' in navigator && location.protocol !== 'file:') {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('./service-worker.js').catch(() => {
      /* Le cache local est facultatif : l'application reste pleinement utilisable en ligne. */
    });
  });
}

if (S.token) charger(); else rendre();
