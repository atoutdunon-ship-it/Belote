/* Démonstration hors-ligne : backend simulé en mémoire.
   Intercepte les appels /api/... de l'interface réelle. Aucune donnée ne sort
   du navigateur ; tout est réinitialisé au rechargement de la page. */
(function () {
  'use strict';

  const NOMS = [
    'Alice Dupont', 'Bruno Marchand', 'Carla Nunez', 'David Legrand',
    'Elodie Perrin', 'Fabien Roche', 'Gisele Amar', 'Hugo Vasseur',
    'Ines Pelletier', 'Jean Morel', 'Karine Bouvier', 'Lucas Ferrand',
    'Maya Toussaint', 'Nicolas Ravel', 'Olivia Sanchez', 'Pierre Garnier',
  ];

  let graine = 20260910;
  const alea = () => ((graine = (graine * 1103515245 + 12345) % 2147483648) / 2147483648);

  const db = { joueurs: [], tournois: [], inscriptions: [], manches: [], tables: [], seqTable: 0 };

  db.joueurs.push({ id: 1, numero: 1, nom: 'Administrateur', pin: '1234', is_admin: true, actif: true });
  NOMS.forEach((nom, i) => db.joueurs.push({
    id: i + 2, numero: 100 + i, nom, pin: String(100 + i).padStart(4, '0'), is_admin: false, actif: true,
  }));

  const tournoi = {
    id: 1, nom: 'Tournoi de démonstration', game_type: 'COINCHE', format: 'MELEE',
    pairing_method: 'SUISSE', nb_joueurs: 16, nb_manches: 3, donnes_par_manche: 10,
    annonces_actives: false, statut: 'EN_COURS',
  };
  db.tournois.push(tournoi);
  NOMS.forEach((_, i) => db.inscriptions.push({
    id: i + 1, tournament_id: 1, player_id: i + 2, dossard: i + 1,
  }));

  const joueur = (id) => db.joueurs.find((j) => j.id === id);
  const inscription = (id) => db.inscriptions.find((i) => i.player_id === id && i.tournament_id === 1);

  /* ------------------------------------------------------------- Calcul */

  function scoreDonne(p, jeu) {
    const TOT = { ATOUT: 162, SANS_ATOUT: 130, TOUT_ATOUT: 258 }[p.trump || 'ATOUT'];
    const preneur = p.taker;
    const defense = preneur === 'NS' ? 'EW' : 'NS';
    const pts = { NS: Number(p.points_ns) || 0, EW: Number(p.points_ew) || 0 };
    const belote = (c) => (p.belote === c ? 20 : 0);
    const scores = { NS: 0, EW: 0 };
    let issue;

    if (jeu === 'CLASSIQUE') {
      if (p.capot) {
        scores[p.capot] = 252 + belote(p.capot);
        scores[p.capot === 'NS' ? 'EW' : 'NS'] = belote(p.capot === 'NS' ? 'EW' : 'NS');
        issue = p.capot === preneur ? 'CAPOT_PRENEUR' : 'CAPOT_DEFENSE';
      } else {
        const bp = pts[preneur] + belote(preneur);
        const bd = pts[defense] + belote(defense);
        if (bp > bd) { issue = 'CONTRAT_REUSSI'; scores[preneur] = bp; scores[defense] = bd; }
        else if (bp < bd) { issue = 'DEDANS'; scores[defense] = 162 + belote(defense); scores[preneur] = belote(preneur); }
        else { issue = 'LITIGE'; scores[defense] = bd; scores[preneur] = belote(preneur); }
      }
      return { ns: scores.NS, ew: scores.EW, detail: { jeu, issue, preneur, atout: p.trump } };
    }

    const norm = (v) => Math.round((v * 162) / TOT);
    const realisePreneur = norm(pts[preneur]) + belote(preneur);
    const realiseDefense = norm(pts[defense]) + belote(defense);
    const contrat = Number(p.contract) || 100;
    const mult = Number(p.multiplier) || 1;
    let reussi;
    let valeur = contrat;
    if (contrat === 500) { reussi = p.capot === preneur; valeur = 500; }
    else if (contrat === 252) { reussi = p.capot === preneur; valeur = 252; }
    else reussi = realisePreneur >= contrat;

    if (reussi) {
      issue = 'CONTRAT_REUSSI';
      scores[preneur] = (valeur + belote(preneur)) * mult;
      scores[defense] = belote(defense) * mult;
    } else {
      issue = 'CHUTE';
      scores[defense] = (pts[defense] + belote(defense)) * mult;
      scores[preneur] = belote(preneur) * mult;
    }
    return {
      ns: scores.NS, ew: scores.EW,
      detail: { jeu, issue, preneur, contrat, atout: p.trump, multiplicateur: mult,
        realise_preneur: realisePreneur, realise_defense: realiseDefense },
    };
  }

  /* ------------------------------------------------------------- Tables */

  function classementBrut() {
    const totaux = {};
    db.inscriptions.forEach((i) => {
      totaux[i.player_id] = { total: 0, per_round: {}, capots_reussis: 0, capots_subis: 0, donnes: 0 };
    });
    db.manches.forEach((m) => m.tables.forEach((t) => t.donnes.forEach((d) => {
      [['NS', t.ns, d.score_ns], ['EW', t.ew, d.score_ew]].forEach(([camp, membres, pts]) => {
        membres.forEach((j) => {
          const e = totaux[j.id];
          if (!e) return;
          e.total += pts;
          e.per_round[m.index] = (e.per_round[m.index] || 0) + pts;
          e.donnes += 1;
          if (d.capot === camp) e.capots_reussis += 1;
          else if (d.capot) e.capots_subis += 1;
        });
      });
    })));
    return totaux;
  }

  function classement() {
    const totaux = classementBrut();
    const lignes = db.inscriptions.map((i) => {
      const e = totaux[i.player_id];
      const manches = Object.values(e.per_round);
      return {
        player_id: i.player_id, dossard: i.dossard, nom: joueur(i.player_id).nom,
        numero: joueur(i.player_id).numero, total: e.total, per_round: e.per_round,
        meilleure_manche: manches.length ? Math.max.apply(null, manches) : 0,
        capots_reussis: e.capots_reussis, capots_subis: e.capots_subis, donnes_jouees: e.donnes,
      };
    });
    lignes.sort((a, b) => b.total - a.total || b.capots_reussis - a.capots_reussis
      || b.meilleure_manche - a.meilleure_manche || a.capots_subis - b.capots_subis
      || a.player_id - b.player_id);
    let rangPrecedent = 0; let clePrecedente = null;
    lignes.forEach((l, i) => {
      const cle = `${l.total}|${l.capots_reussis}|${l.meilleure_manche}|${l.capots_subis}`;
      if (cle === clePrecedente) l.rank = rangPrecedent;
      else { l.rank = i + 1; clePrecedente = cle; rangPrecedent = i + 1; }
    });
    return lignes;
  }

  function nouvelleManche() {
    const ordre = db.manches.length
      ? classement().map((l) => l.player_id)
      : db.inscriptions.map((i) => i.player_id);
    const index = db.manches.length + 1;
    const manche = { id: index, index, statut: 'EN_COURS', tables: [] };
    for (let i = 0; i < ordre.length; i += 4) {
      const g = ordre.slice(i, i + 4).map((id) => ({
        id, nom: joueur(id).nom, dossard: inscription(id).dossard,
      }));
      db.seqTable += 1;
      manche.tables.push({
        id: db.seqTable, numero: i / 4 + 1, ns: [g[0], g[3]], ew: [g[1], g[2]],
        captain_id: g[0].id, donnes: [], donnes_attendues: tournoi.donnes_par_manche,
        manche: index,
      });
    }
    db.manches.push(manche);
    return manche;
  }

  function recalculer(table) {
    table.donnes.forEach((d) => {
      const r = scoreDonne(d.saisie, tournoi.game_type);
      d.score_ns = r.ns; d.score_ew = r.ew; d.detail = r.detail; d.capot = d.saisie.capot || null;
    });
  }

  function serialiser(table) {
    return {
      id: table.id, numero: table.numero, ns: table.ns, ew: table.ew,
      captain_id: table.captain_id, manche: table.manche,
      total_ns: table.donnes.reduce((s, d) => s + d.score_ns, 0),
      total_ew: table.donnes.reduce((s, d) => s + d.score_ew, 0),
      donnes_attendues: table.donnes_attendues,
      donnes: table.donnes.map((d) => ({
        id: d.index, index: d.index, score_ns: d.score_ns, score_ew: d.score_ew,
        carry: 0, capot: d.capot, saisie: d.saisie, detail: d.detail,
      })),
    };
  }

  /* Manche 1 pré-remplie pour que la démonstration ait de la matière. */
  const premiere = nouvelleManche();
  premiere.tables.forEach((t) => {
    for (let i = 1; i <= tournoi.donnes_par_manche; i += 1) {
      const preneur = alea() < 0.5 ? 'NS' : 'EW';
      const capot = alea() < 0.06 ? (alea() < 0.5 ? 'NS' : 'EW') : null;
      let pns;
      if (capot) pns = capot === 'NS' ? 162 : 0;
      else {
        const p = 40 + Math.floor(alea() * 122);
        pns = preneur === 'NS' ? p : 162 - p;
      }
      t.donnes.push({
        index: i,
        saisie: {
          index: i, taker: preneur, trump: 'ATOUT', points_ns: pns, points_ew: 162 - pns,
          contract: capot ? 252 : [80, 90, 100, 110, 120, 130][Math.floor(alea() * 6)],
          multiplier: alea() < 0.12 ? 2 : 1, belote: null, capot, generale: false,
          declarations_ns: [], declarations_ew: [],
        },
      });
    }
    recalculer(t);
  });
  premiere.statut = 'CLOTUREE';
  nouvelleManche();

  /* ---------------------------------------------------------- Dispatcher */

  const json = (corps, statut) => new Response(
    corps === null ? '' : JSON.stringify(corps),
    { status: statut || 200, headers: { 'Content-Type': 'application/json' } },
  );
  const erreur = (msg, statut) => json({ detail: msg }, statut || 400);

  const resume = () => ({
    id: tournoi.id, nom: tournoi.nom, game_type: tournoi.game_type, format: tournoi.format,
    pairing_method: tournoi.pairing_method, nb_joueurs: tournoi.nb_joueurs,
    nb_manches: tournoi.nb_manches, donnes_par_manche: tournoi.donnes_par_manche,
    annonces_actives: tournoi.annonces_actives, statut: tournoi.statut,
    inscrits: db.inscriptions.length, manches_jouees: db.manches.length,
  });

  function traiter(methode, chemin, corps, moi) {
    if (methode === 'POST' && chemin === '/auth/login') {
      const j = db.joueurs.find((x) => x.numero === Number(corps.numero) && x.pin === String(corps.pin));
      if (!j) return erreur('Numéro de joueur ou code PIN incorrect.', 401);
      return json({ access_token: `demo-${j.id}`, token_type: 'bearer', player_id: j.id,
        numero: j.numero, nom: j.nom, is_admin: j.is_admin });
    }
    if (!moi) return erreur('Authentification requise.', 401);

    if (methode === 'GET' && chemin === '/auth/me') {
      return json({ id: moi.id, numero: moi.numero, nom: moi.nom, is_admin: moi.is_admin, actif: true });
    }
    if (methode === 'POST' && chemin === '/auth/pin') {
      if (String(corps.ancien_pin) !== moi.pin) return erreur('Code PIN actuel incorrect.');
      if (!/^\d{4}$/.test(String(corps.nouveau_pin))) return erreur('Le code PIN doit comporter 4 chiffres.');
      moi.pin = String(corps.nouveau_pin);
      return json(null, 204);
    }
    if (methode === 'GET' && chemin === '/tournaments') return json([resume()]);
    if (methode === 'GET' && chemin === '/tournaments/1') return json(resume());
    if (methode === 'POST' && chemin === '/tournaments') {
      return erreur('Démonstration : la création d\'un nouveau tournoi est désactivée. '
        + 'Toutes les autres fonctions sont actives.');
    }
    if (chemin === '/players') {
      if (!moi.is_admin) return erreur('Réservé à l\'administrateur.', 403);
      if (methode === 'GET') {
        return json(db.joueurs.map((j) => ({ id: j.id, numero: j.numero, nom: j.nom,
          is_admin: j.is_admin, actif: j.actif })));
      }
      return erreur('Démonstration : ajout de joueur désactivé.');
    }
    if (chemin === '/tournaments/1/registrations') {
      if (!moi.is_admin) return erreur('Réservé à l\'administrateur.', 403);
      if (methode === 'GET') {
        return json(db.inscriptions.map((i) => ({ id: i.id, player_id: i.player_id,
          numero: joueur(i.player_id).numero, nom: joueur(i.player_id).nom,
          dossard: i.dossard, team_numero: null, team_nom: null })));
      }
      return erreur('Démonstration : les inscriptions sont figées (effectif complet).');
    }
    if (chemin === '/tournaments/1/rounds' && methode === 'GET') {
      if (!moi.is_admin) return erreur('Réservé à l\'administrateur.', 403);
      return json(db.manches.map((m) => ({ id: m.id, index: m.index, statut: m.statut,
        tables: m.tables.map(serialiser) })));
    }
    if (chemin === '/tournaments/1/rounds' && methode === 'POST') {
      if (!moi.is_admin) return erreur('Réservé à l\'administrateur.', 403);
      const derniere = db.manches[db.manches.length - 1];
      if (derniere && derniere.statut !== 'CLOTUREE') {
        return erreur(`La manche ${derniere.index} doit être clôturée avant d'en créer une nouvelle.`);
      }
      if (db.manches.length >= tournoi.nb_manches) {
        return erreur(`Le tournoi ne comporte que ${tournoi.nb_manches} manches.`);
      }
      const m = nouvelleManche();
      return json({ id: m.id, index: m.index, statut: m.statut, tables: m.tables.map(serialiser) });
    }
    let corr = chemin.match(/^\/tournaments\/1\/rounds\/(\d+)\/close$/);
    if (corr && methode === 'POST') {
      if (!moi.is_admin) return erreur('Réservé à l\'administrateur.', 403);
      const m = db.manches.find((x) => x.index === Number(corr[1]));
      if (!m) return erreur('Manche introuvable.', 404);
      const incomplets = m.tables.filter((t) => t.donnes.length < tournoi.donnes_par_manche)
        .map((t) => t.numero);
      if (incomplets.length) {
        return erreur(`Manche incomplète : tables ${incomplets.join(', ')} `
          + `(il faut ${tournoi.donnes_par_manche} donnes par table).`);
      }
      m.statut = 'CLOTUREE';
      if (m.index >= tournoi.nb_manches) tournoi.statut = 'TERMINE';
      return json({ id: m.id, index: m.index, statut: m.statut, tables: m.tables.map(serialiser) });
    }
    if (chemin === '/tournaments/1/standings' && methode === 'GET') {
      if (!moi.is_admin && tournoi.statut !== 'TERMINE') {
        return erreur('Le classement complet est publié à la fin du tournoi.', 403);
      }
      return json({ tournoi: resume(), joueurs: classement() });
    }
    if (chemin === '/tournaments/1/standings/me' && methode === 'GET') {
      const ligne = classement().find((l) => l.player_id === moi.id);
      if (!ligne) return erreur('Vous n\'êtes pas inscrit à ce tournoi.', 404);
      ligne.participants = tournoi.nb_joueurs;
      const detail = [];
      db.manches.forEach((m) => m.tables.forEach((t) => {
        const camp = t.ns.some((j) => j.id === moi.id) ? 'NS'
          : (t.ew.some((j) => j.id === moi.id) ? 'EW' : null);
        if (!camp) return;
        detail.push({
          manche: m.index, table: t.numero, camp,
          donnes: t.donnes.map((d) => ({ index: d.index,
            points: camp === 'NS' ? d.score_ns : d.score_ew,
            points_adverses: camp === 'NS' ? d.score_ew : d.score_ns,
            issue: (d.detail || {}).issue, capot: d.capot })),
          total: t.donnes.reduce((s, d) => s + (camp === 'NS' ? d.score_ns : d.score_ew), 0),
        });
      }));
      return json({ tournoi: resume(), classement: ligne, detail,
        classement_publie: tournoi.statut === 'TERMINE' });
    }
    if (chemin === '/tournaments/1/me/table' && methode === 'GET') {
      const m = db.manches.slice().reverse().find((x) => x.statut === 'EN_COURS');
      if (!m) return erreur('Aucune manche en cours.', 404);
      const t = m.tables.find((x) => x.ns.concat(x.ew).some((j) => j.id === moi.id));
      if (!t) return erreur('Vous n\'êtes pas attablé sur cette manche.', 404);
      const p = serialiser(t);
      p.est_capitaine = t.captain_id === moi.id || moi.is_admin;
      p.mon_camp = t.ns.some((j) => j.id === moi.id) ? 'NS' : 'EW';
      return json(p);
    }
    corr = chemin.match(/^\/tables\/(\d+)\/deals$/);
    if (corr && methode === 'POST') {
      const table = db.manches.flatMap((m) => m.tables).find((t) => t.id === Number(corr[1]));
      if (!table) return erreur('Table introuvable.', 404);
      const manche = db.manches.find((m) => m.tables.includes(table));
      if (manche.statut === 'CLOTUREE') return erreur('La manche est clôturée : la saisie est verrouillée.');
      if (!moi.is_admin && moi.id !== table.captain_id) {
        return erreur('Seuls le capitaine de table et l\'administrateur peuvent saisir une donne.', 403);
      }
      const total = { ATOUT: 162, SANS_ATOUT: 130, TOUT_ATOUT: 258 }[corps.trump || 'ATOUT'];
      if (!corps.capot && Number(corps.points_ns) + Number(corps.points_ew) !== total) {
        return erreur(`La somme des points doit valoir ${total} `
          + `(saisi : ${corps.points_ns} + ${corps.points_ew}).`);
      }
      const existante = table.donnes.find((d) => d.index === Number(corps.index));
      if (existante) existante.saisie = corps;
      else table.donnes.push({ index: Number(corps.index), saisie: corps });
      table.donnes.sort((a, b) => a.index - b.index);
      recalculer(table);
      return json(serialiser(table));
    }
    corr = chemin.match(/^\/tables\/(\d+)\/deals\/(\d+)$/);
    if (corr && methode === 'DELETE') {
      if (!moi.is_admin) return erreur('Réservé à l\'administrateur.', 403);
      const table = db.manches.flatMap((m) => m.tables).find((t) => t.id === Number(corr[1]));
      if (!table) return erreur('Table introuvable.', 404);
      table.donnes = table.donnes.filter((d) => d.index !== Number(corr[2]));
      recalculer(table);
      return json(serialiser(table));
    }
    corr = chemin.match(/^\/tables\/(\d+)$/);
    if (corr && methode === 'GET') {
      const table = db.manches.flatMap((m) => m.tables).find((t) => t.id === Number(corr[1]));
      if (!table) return erreur('Table introuvable.', 404);
      const p = serialiser(table);
      p.est_capitaine = table.captain_id === moi.id || moi.is_admin;
      return json(p);
    }
    return erreur('Point d\'accès non disponible en démonstration.', 404);
  }

  const fetchOrigine = window.fetch.bind(window);
  window.fetch = function (url, options) {
    const chaine = String(url);
    if (chaine.indexOf('/api') !== 0) return fetchOrigine(url, options);
    const opts = options || {};
    const entetes = opts.headers || {};
    const jeton = entetes.Authorization || entetes.authorization || '';
    const moi = jeton ? joueur(Number(String(jeton).replace('Bearer demo-', ''))) : null;
    let corps = {};
    try { corps = opts.body ? JSON.parse(opts.body) : {}; } catch (e) { corps = {}; }
    return Promise.resolve(
      traiter(opts.method || 'GET', chaine.slice(4), corps, moi || null)
    );
  };

  window.WebSocket = function () { throw new Error('WebSocket indisponible en démonstration.'); };
})();
