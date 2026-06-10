/* plant3d.js — 3D 가상 공장 렌더러 v3 (Three.js r160, PBR/PMREM 급).
 *
 * v3 렌더링 계층: ACES 톤매핑 + sRGB + PMREM 환경반사(절차 환경맵, 외부 에셋 0)
 * + 절차적 캔버스 텍스처(콘크리트 바닥·체커플레이트 통로·황흑 위험띠) + 부드러운
 * 그림자. 공장 구조: I빔 기둥/트러스 보·파이프랙·케이블트레이·가드레일·PLC 캐비닛.
 * 설비 연결: 플랜지 배관(흐름 입자)·전선관(통전 발광). 기기 모델 정밀화(모터
 * 냉각핀/단자함, 펌프 볼류트, 플랜지 탱크+레벨게이지, 컨베이어 사이드프레임/롤러).
 *
 * window.Plant3D.create(container, plant, {onToggle}) ->
 *   { update(simResult), resize(), destroy() }
 */
(function () {
  "use strict";
  if (!window.THREE) { window.Plant3D = null; return; }
  var T = window.THREE;

  var COL = {
    steel: 0xb8c2cd, steelDark: 0x55606c, blue: 0x3b7dd8, blueDeep: 0x2c5fa8,
    safety: 0xd6a416, on: 0x35e070, red: 0xff4040, amber: 0xe0a020,
    water: 0x3585f0, glass: 0xbcd2e8, pipe: 0x9aa8b8, cable: 0x222a33,
    cabinet: 0x3c5e8f, concrete: 0x55585e, frame: 0x6f7b88,
  };

  // ── 절차적 텍스처 (외부 에셋 0) ─────────────────────────────────────────────
  function canvasTex(w, h, draw, repx, repy) {
    var c = document.createElement("canvas"); c.width = w; c.height = h;
    draw(c.getContext("2d"), w, h);
    var tx = new T.CanvasTexture(c);
    tx.wrapS = tx.wrapT = T.RepeatWrapping;
    tx.repeat.set(repx || 1, repy || 1);
    tx.anisotropy = 4;
    return tx;
  }
  function texConcrete() {
    return canvasTex(256, 256, function (g, w, h) {
      g.fillStyle = "#5a5d63"; g.fillRect(0, 0, w, h);
      for (var i = 0; i < 2600; i++) {
        var v = 78 + Math.random() * 28 | 0;
        g.fillStyle = "rgb(" + v + "," + (v + 1) + "," + (v + 4) + ")";
        g.fillRect(Math.random() * w, Math.random() * h, 1.6, 1.6);
      }
      g.strokeStyle = "rgba(28,30,34,.5)"; g.lineWidth = 2;     // 신축줄눈
      g.strokeRect(0, 0, w, h);
    }, 7, 7);
  }
  function texChecker() {
    return canvasTex(128, 128, function (g, w, h) {
      g.fillStyle = "#76808c"; g.fillRect(0, 0, w, h);
      g.fillStyle = "rgba(255,255,255,.16)";
      for (var y = 0; y < 4; y++) for (var x = 0; x < 4; x++) {
        g.save();
        g.translate(x * 32 + 16, y * 32 + 16);
        g.rotate(((x + y) % 2) ? Math.PI / 4 : -Math.PI / 4);
        g.fillRect(-9, -2.4, 18, 4.8);
        g.restore();
      }
    }, 6, 1.2);
  }
  function texHazard() {
    return canvasTex(128, 32, function (g, w, h) {
      g.fillStyle = "#caa110"; g.fillRect(0, 0, w, h);
      g.fillStyle = "#15161a";
      for (var x = -32; x < w + 32; x += 32) {
        g.beginPath();
        g.moveTo(x, h); g.lineTo(x + 16, 0); g.lineTo(x + 32, 0); g.lineTo(x + 16, h);
        g.closePath(); g.fill();
      }
    }, 8, 1);
  }

  function mat(color, o) {
    o = o || {};
    return new T.MeshStandardMaterial({
      color: color, roughness: o.rough != null ? o.rough : .5,
      metalness: o.metal != null ? o.metal : .55,
      transparent: !!o.alpha, opacity: o.alpha || 1,
      emissive: o.emissive || 0x000000, emissiveIntensity: o.ei != null ? o.ei : 1,
      map: o.map || null, envMapIntensity: o.envI != null ? o.envI : 1,
      side: o.side || T.FrontSide,
    });
  }
  function box(w, h, d, m) { var x = new T.Mesh(new T.BoxGeometry(w, h, d), m); x.castShadow = true; return x; }
  function cyl(rt, rb, h, m, seg) {
    var x = new T.Mesh(new T.CylinderGeometry(rt, rb, h, seg || 26), m);
    x.castShadow = true; return x;
  }
  function torus(r, t2, m, arc) {
    var x = new T.Mesh(new T.TorusGeometry(r, t2, 12, 30, arc || Math.PI * 2), m);
    x.castShadow = true; return x;
  }

  function labelSprite(text, sub) {
    var c = document.createElement("canvas");
    var g = c.getContext("2d");
    g.font = "700 30px system-ui, sans-serif";
    var w = Math.max(Math.ceil(g.measureText(text).width),
      sub ? g.measureText(sub).width * .66 : 0) + 30;
    var h = sub ? 64 : 46;
    c.width = w; c.height = h;
    g = c.getContext("2d");
    g.fillStyle = "rgba(8,12,18,.85)";
    g.beginPath();
    if (g.roundRect) g.roundRect(0, 0, w, h, 11); else g.rect(0, 0, w, h);
    g.fill();
    g.strokeStyle = "rgba(140,170,205,.5)"; g.stroke();
    g.fillStyle = "#eaf2fb"; g.font = "700 30px system-ui, sans-serif";
    g.fillText(text, 14, 33);
    if (sub) { g.fillStyle = "#8b9aab"; g.font = "500 19px system-ui, sans-serif"; g.fillText(sub, 14, 55); }
    var sp = new T.Sprite(new T.SpriteMaterial({ map: new T.CanvasTexture(c), depthTest: false }));
    sp.scale.set(w / 130, h / 130, 1);
    return sp;
  }

  // I빔 단면 기둥/보 (Extrude)
  function iBeam(len, size, m, horizontal) {
    var s = size || .26, f = s * .5, wb = s * .09;
    var sh = new T.Shape();
    sh.moveTo(-f, -s / 2); sh.lineTo(f, -s / 2); sh.lineTo(f, -s / 2 + wb * 1.4);
    sh.lineTo(wb, -s / 2 + wb * 1.4); sh.lineTo(wb, s / 2 - wb * 1.4);
    sh.lineTo(f, s / 2 - wb * 1.4); sh.lineTo(f, s / 2); sh.lineTo(-f, s / 2);
    sh.lineTo(-f, s / 2 - wb * 1.4); sh.lineTo(-wb, s / 2 - wb * 1.4);
    sh.lineTo(-wb, -s / 2 + wb * 1.4); sh.lineTo(-f, -s / 2 + wb * 1.4);
    sh.closePath();
    var geo = new T.ExtrudeGeometry(sh, { depth: len, bevelEnabled: false });
    var mesh = new T.Mesh(geo, m);
    if (horizontal) mesh.rotation.y = Math.PI / 2;
    else mesh.rotation.x = -Math.PI / 2;
    mesh.castShadow = true;
    return mesh;
  }

  // 플랜지 배관 — 경유점 따라 튜브 + 굽이마다 플랜지 디스크
  function flangedPipe(scene, pts, radius, m) {
    var curve = new T.CatmullRomCurve3(pts, false, "catmullrom", .04);
    var tube = new T.Mesh(new T.TubeGeometry(curve, 50, radius, 12), m);
    tube.castShadow = true; scene.add(tube);
    pts.forEach(function (p, i) {
      if (i === 0 || i === pts.length - 1) return;
      var fl = cyl(radius * 1.7, radius * 1.7, radius * .9, m);
      fl.position.copy(p);
      scene.add(fl);
    });
    return curve;
  }

  // ── 기기 빌더 — {group, anim(on, t, dt)} ──────────────────────────────────
  function bMotor() {
    var g = new T.Group();
    var base = box(1.2, .22, .9, mat(0x3a3d44, { rough: .8, metal: .25 })); base.position.y = .11; g.add(base);
    var body = cyl(.34, .34, .9, mat(COL.blue, { metal: .65, rough: .32 }));
    body.rotation.z = Math.PI / 2; body.position.y = .58; g.add(body);
    for (var i = 0; i < 9; i++) {                                   // 방사 냉각핀
      var fin = box(.86, .015, .76, mat(COL.blueDeep, { metal: .6, rough: .4 }));
      fin.position.y = .58; fin.rotation.x = (i / 9) * Math.PI; g.add(fin);
    }
    var jbox = box(.26, .2, .3, mat(COL.steelDark, { metal: .5 })); jbox.position.set(0, .95, 0); g.add(jbox);
    var endb = cyl(.36, .36, .12, mat(COL.steelDark, { metal: .6 }));
    endb.rotation.z = Math.PI / 2; endb.position.set(-.48, .58, 0); g.add(endb);
    var ring = torus(.3, .035, mat(0x111418, { emissive: COL.on, ei: 0 }));
    ring.rotation.y = Math.PI / 2; ring.position.set(-.55, .58, 0); g.add(ring);
    var shaft = cyl(.05, .05, .34, mat(0xd9e2ec, { metal: .9, rough: .18 }));
    shaft.rotation.z = Math.PI / 2; shaft.position.set(.6, .58, 0); g.add(shaft);
    var rotor = new T.Group(); rotor.position.set(.8, .58, 0);
    var hub = cyl(.09, .09, .12, mat(COL.steelDark, { metal: .7 }));
    hub.rotation.z = Math.PI / 2; rotor.add(hub);
    for (var k = 0; k < 3; k++) {
      var bl = box(.05, .5, .14, mat(0xe8eef5, { metal: .35, rough: .3 }));
      bl.position.y = .26; var hold = new T.Group();
      hold.rotation.x = k * Math.PI * 2 / 3; hold.add(bl); rotor.add(hold);
    }
    rotor.rotation.z = Math.PI / 2; g.add(rotor);
    return { group: g, anim: function (on, t, dt) {
      if (on) rotor.rotateOnAxis(new T.Vector3(0, 1, 0), dt * 11);
      ring.material.emissiveIntensity = on ? 1.6 : 0;
    } };
  }
  function bPump() {
    var g = new T.Group();
    var base = box(1.05, .2, .9, mat(0x3a3d44, { rough: .8, metal: .25 })); base.position.y = .1; g.add(base);
    var vol = new T.Mesh(new T.LatheGeometry([                      // 볼류트 곡면
      new T.Vector2(.06, 0), new T.Vector2(.42, .04), new T.Vector2(.46, .22),
      new T.Vector2(.4, .42), new T.Vector2(.22, .55), new T.Vector2(.07, .58),
    ], 26), mat(COL.blue, { metal: .6, rough: .3 }));
    vol.position.y = .22; vol.castShadow = true; g.add(vol);
    var suct = cyl(.12, .12, .5, mat(COL.pipe, { metal: .7, rough: .3 }));
    suct.rotation.z = Math.PI / 2; suct.position.set(-.6, .42, 0); g.add(suct);
    var sfl = cyl(.18, .18, .05, mat(COL.pipe, { metal: .7 }));
    sfl.rotation.z = Math.PI / 2; sfl.position.set(-.84, .42, 0); g.add(sfl);
    var outp = cyl(.11, .11, .5, mat(COL.pipe, { metal: .7, rough: .3 }));
    outp.position.set(0, .95, 0); g.add(outp);
    var mot = cyl(.2, .2, .5, mat(COL.steel, { metal: .6, rough: .35 }));
    mot.rotation.z = Math.PI / 2; mot.position.set(.55, .42, 0); g.add(mot);
    var lamp = new T.Mesh(new T.SphereGeometry(.07, 14, 10), mat(COL.on, { emissive: COL.on, ei: 0 }));
    lamp.position.set(.55, .72, 0); g.add(lamp);
    return { group: g, anim: function (on, t) {
      lamp.material.emissiveIntensity = on ? 1.3 + Math.sin(t * 14) * .4 : 0;
    } };
  }
  function bValve() {
    var g = new T.Group();
    var pipe = cyl(.14, .14, 1.7, mat(COL.pipe, { metal: .7, rough: .3 }));
    pipe.rotation.z = Math.PI / 2; pipe.position.y = .5; g.add(pipe);
    [-0.62, 0.62].forEach(function (x) {
      var fl = cyl(.2, .2, .06, mat(COL.pipe, { metal: .7 }));
      fl.rotation.z = Math.PI / 2; fl.position.set(x, .5, 0); g.add(fl);
    });
    var bodyV = new T.Mesh(new T.SphereGeometry(.24, 18, 14), mat(COL.blueDeep, { metal: .55, rough: .35 }));
    bodyV.position.y = .5; bodyV.castShadow = true; g.add(bodyV);
    var bonnet = cyl(.1, .14, .3, mat(COL.steel, { metal: .6 })); bonnet.position.y = .78; g.add(bonnet);
    var act = box(.46, .3, .34, mat(COL.safety, { metal: .35, rough: .45 })); act.position.y = 1.08; g.add(act);
    var ind = box(.06, .14, .06, mat(COL.red, { emissive: COL.red, ei: .4 }));
    ind.position.y = 1.3; g.add(ind);
    return { group: g, anim: function (on, t, dt) {
      var target = on ? Math.PI / 2 : 0;
      ind.rotation.y += (target - ind.rotation.y) * Math.min(1, dt * 5);
      ind.material.color.set(on ? COL.on : COL.red);
      ind.material.emissive.set(on ? COL.on : COL.red);
    } };
  }
  function bHeater() {
    var g = new T.Group();
    var body = box(1.05, 1.15, .9, mat(0x6b4a33, { rough: .55, metal: .35 })); body.position.y = .6; g.add(body);
    [-0.3, 0, 0.3].forEach(function (y) {
      var band = box(1.07, .05, .92, mat(COL.steelDark, { metal: .6 }));
      band.position.y = .6 + y; g.add(band);
    });
    var win = box(.66, .42, .03, mat(0x140a05, { rough: .25, metal: .1 }));
    win.position.set(0, .7, .46); g.add(win);
    var coil = box(.56, .3, .02, mat(0xff5a1f, { emissive: 0xff4a10, ei: 0 }));
    coil.position.set(0, .7, .465); g.add(coil);
    var stack = cyl(.09, .11, .6, mat(COL.pipe, { metal: .6 })); stack.position.set(.32, 1.45, 0); g.add(stack);
    return { group: g, anim: function (on, t) {
      coil.material.emissiveIntensity = on ? 1.8 + Math.sin(t * 7) * .45 : 0;
    } };
  }
  function bFan() {
    var g = new T.Group();
    var pole = cyl(.07, .1, 1.15, mat(COL.frame, { metal: .55 })); pole.position.y = .57; g.add(pole);
    var ringG = torus(.52, .05, mat(COL.steelDark, { metal: .6 })); ringG.position.y = 1.3; g.add(ringG);
    var grill = new T.Group(); grill.position.y = 1.3;
    for (var gi = 0; gi < 5; gi++) {
      var gr = torus(.1 + gi * .1, .008, mat(COL.steelDark, { metal: .5 })); grill.add(gr);
    }
    g.add(grill);
    var hub = new T.Group(); hub.position.y = 1.3; hub.position.z = .04;
    for (var i = 0; i < 5; i++) {
      var bl = box(.1, .4, .02, mat(0x9fd4ff, { metal: .3, rough: .3 }));
      bl.position.y = .26; bl.rotation.y = .5;
      var hold = new T.Group();
      hold.rotation.z = i * Math.PI * 2 / 5; hold.add(bl); hub.add(hold);
    }
    g.add(hub);
    return { group: g, anim: function (on, t, dt) {
      if (on) hub.rotateOnAxis(new T.Vector3(0, 0, 1), dt * 12);
    } };
  }
  function bConveyor(d, ctx) {
    var g = new T.Group();
    [-0.42, 0.42].forEach(function (z) {                           // 사이드 프레임
      var fr = box(2.6, .16, .05, mat(COL.blueDeep, { metal: .55, rough: .35 }));
      fr.position.set(0, .62, z); g.add(fr);
    });
    for (var rx = -1.15; rx <= 1.16; rx += .23) {                  // 롤러 배열
      var roll = cyl(.05, .05, .8, mat(0xc8d2dd, { metal: .8, rough: .25 }));
      roll.rotation.x = Math.PI / 2; roll.position.set(rx, .6, 0); g.add(roll);
    }
    [-1, 1].forEach(function (x) {
      [-0.32, 0.32].forEach(function (z) {
        var leg = box(.07, .56, .07, mat(COL.frame, { metal: .5 })); leg.position.set(x, .28, z); g.add(leg);
      });
    });
    var items = [];
    if (!(ctx && ctx.line)) {
      for (var i = 0; i < 4; i++) {                                // 흐르는 제품(병)
        var it = cyl(.085, .085, .26, mat(COL.glass, { alpha: .55, rough: .15, metal: .1 }));
        var cap = cyl(.05, .05, .05, mat(COL.blue, { metal: .4 })); cap.position.y = .155; it.add(cap);
        it.position.set(-1.1 + i * .58, .8, 0); g.add(it); items.push(it);
      }
    }
    return { group: g, anim: function (on, t, dt) {
      if (!on) return;
      items.forEach(function (it) {
        it.position.x += dt * 1.15;
        if (it.position.x > 1.2) it.position.x = -1.2;
      });
    } };
  }
  function bBeacon() {
    var g = new T.Group();
    var pole = cyl(.045, .06, 1.6, mat(COL.frame, { metal: .6 })); pole.position.y = .8; g.add(pole);
    var stack = [[COL.red, 1.78], [COL.amber, 1.62], [COL.on, 1.46]];
    var lamps = [];
    stack.forEach(function (st) {
      var seg = cyl(.1, .1, .15, mat(st[0], { emissive: st[0], ei: .12, alpha: .92 }));
      seg.position.y = st[1]; g.add(seg); lamps.push(seg);
    });
    var light = new T.PointLight(COL.red, 0, 8); light.position.y = 1.8; g.add(light);
    return { group: g, anim: function (on, t) {
      var f = on ? (Math.sin(t * 11) > 0 ? 2.2 : .12) : .12;
      lamps[0].material.emissiveIntensity = f;
      light.intensity = on ? (Math.sin(t * 11) > 0 ? 2.4 : 0) : 0;
    } };
  }
  function bEjector() {
    var g = new T.Group();
    var base = box(.6, .5, .55, mat(COL.steelDark, { metal: .55 })); base.position.y = .3; g.add(base);
    var cylBody = cyl(.11, .11, .55, mat(COL.blue, { metal: .6, rough: .3 }));
    cylBody.rotation.x = Math.PI / 2; cylBody.position.set(0, .5, .35); g.add(cylBody);
    [-0.18, 0.18].forEach(function (dy) {
      var rod2 = cyl(.018, .018, .55, mat(0xd9e2ec, { metal: .85, rough: .2 }));
      rod2.rotation.x = Math.PI / 2; rod2.position.set(dy, .5, .35); g.add(rod2);
    });
    var rod = cyl(.045, .045, .62, mat(0xd9e2ec, { metal: .9, rough: .15 }));
    rod.rotation.x = Math.PI / 2; rod.position.set(0, .5, .8); g.add(rod);
    var head = box(.46, .42, .08, mat(COL.safety, { rough: .45, metal: .3 })); head.position.set(0, .5, 1.1); g.add(head);
    return { group: g, anim: function (on, t, dt) {
      var target = on ? 1.5 : 1.1;
      head.position.z += (target - head.position.z) * Math.min(1, dt * 8);
      rod.position.z = (head.position.z + .5) / 2 - .12;
    } };
  }
  function bGate() {
    var g = new T.Group();
    [-0.62, 0.62].forEach(function (x) {
      var post = box(.14, 1.6, .14, mat(COL.safety, { rough: .5, metal: .3 })); post.position.set(x, .8, 0); g.add(post);
    });
    var beam = box(1.4, .14, .14, mat(COL.safety, { rough: .5, metal: .3 })); beam.position.y = 1.6; g.add(beam);
    var panel = box(1.1, 1.05, .05, mat(COL.steel, { metal: .65, rough: .3, alpha: .94 }));
    panel.position.y = .58; g.add(panel);
    return { group: g, anim: function (on, t, dt) {
      var target = on ? 1.35 : .58;
      panel.position.y += (target - panel.position.y) * Math.min(1, dt * 6);
    } };
  }
  function bMixer() {
    var g = new T.Group();
    var vessel = cyl(.52, .42, 1, mat(COL.glass, { alpha: .35, rough: .12, metal: .15 }));
    vessel.position.y = .6; g.add(vessel);
    var rim = torus(.52, .03, mat(COL.steel, { metal: .65 })); rim.rotation.x = Math.PI / 2; rim.position.y = 1.1; g.add(rim);
    var top = box(.56, .12, .56, mat(COL.steelDark, { metal: .55 })); top.position.y = 1.2; g.add(top);
    var mot = cyl(.15, .15, .34, mat(COL.blue, { metal: .55 })); mot.position.y = 1.45; g.add(mot);
    var shaft = new T.Group(); shaft.position.y = .65;
    var rodS = cyl(.03, .03, 1, mat(0xd9e2ec, { metal: .85, rough: .2 })); rodS.position.y = .22; shaft.add(rodS);
    [-.18, .18].forEach(function (y2) {
      var blade = box(.64, .06, .1, mat(0xd9e2ec, { metal: .8, rough: .25 })); blade.position.y = y2; shaft.add(blade);
    });
    g.add(shaft);
    return { group: g, anim: function (on, t, dt) {
      if (on) shaft.rotateOnAxis(new T.Vector3(0, 1, 0), dt * 8);
    } };
  }
  function bActuator() {
    var g = new T.Group();
    var body = box(.8, .8, .8, mat(COL.steelDark, { metal: .5, emissive: COL.on, ei: 0 }));
    body.position.y = .42; g.add(body);
    var ind = box(.16, .06, .02, mat(COL.on, { emissive: COL.on, ei: .15 }));
    ind.position.set(0, .68, .42); g.add(ind);
    return { group: g, anim: function (on) {
      body.material.emissiveIntensity = on ? .35 : 0;
      ind.material.emissiveIntensity = on ? 1.6 : .15;
    } };
  }
  function bTank() {
    var g = new T.Group();
    for (var li = 0; li < 4; li++) {
      var leg = box(.1, .55, .1, mat(COL.frame, { metal: .55 }));
      var a = li * Math.PI / 2 + Math.PI / 4;
      leg.position.set(Math.cos(a) * .52, .27, Math.sin(a) * .52); g.add(leg);
    }
    var shell = cyl(.66, .66, 1.7, mat(COL.steel, { metal: .35, rough: .3, alpha: .35 }));
    shell.position.y = 1.4; shell.castShadow = false; g.add(shell);
    [-0.62, 0.62].forEach(function (y2) {
      var weld = torus(.665, .012, mat(COL.steel, { metal: .6 }));
      weld.rotation.x = Math.PI / 2; weld.position.y = 1.4 + y2; g.add(weld);
    });
    var cap = new T.Mesh(new T.SphereGeometry(.66, 26, 12, 0, Math.PI * 2, 0, Math.PI / 2),
      mat(COL.steel, { metal: .45, rough: .3 }));
    cap.position.y = 2.25; cap.castShadow = true; g.add(cap);
    var manway = cyl(.16, .16, .1, mat(COL.steelDark, { metal: .6 }));
    manway.position.set(.3, 2.42, .2); g.add(manway);
    var water = cyl(.6, .6, 1, mat(COL.water, { alpha: .8, rough: .2, metal: 0 }));
    water.position.y = .9; water.scale.y = .35; water.castShadow = false; g.add(water);
    var nozzle = cyl(.09, .09, .5, mat(COL.pipe, { metal: .7 }));
    nozzle.position.set(0, 2.5, 0); g.add(nozzle);
    // 사이트 레벨 게이지(투명관 + 수위)
    var sight = cyl(.04, .04, 1.5, mat(COL.glass, { alpha: .3, rough: .1 }));
    sight.position.set(.74, 1.4, 0); g.add(sight);
    var sightw = cyl(.03, .03, 1, mat(COL.water, { alpha: .9 }));
    sightw.position.set(.74, .95, 0); sightw.scale.y = .35; g.add(sightw);
    var level = .35;
    return { group: g, anim: function (on, t, dt) {
      level = Math.max(.06, Math.min(.95, level + (on ? .1 : -.045) * dt));
      water.scale.y = level;
      water.position.y = .55 + level * 1.65 / 2 + .05;
      sightw.scale.y = level;
      sightw.position.y = .62 + level * 1.5 / 2;
    } };
  }
  function bGauge() {
    var g = new T.Group();
    var pole = box(.1, 1.3, .1, mat(COL.frame, { metal: .55 })); pole.position.y = .65; g.add(pole);
    var head = cyl(.3, .3, .12, mat(0xe8edf3, { metal: .25, rough: .35 }));
    head.rotation.x = Math.PI / 2; head.position.y = 1.55; g.add(head);
    var face = cyl(.26, .26, .02, mat(0xf4f7fa, { metal: 0, rough: .6 }));
    face.rotation.x = Math.PI / 2; face.position.set(0, 1.55, .06); g.add(face);
    var needle = box(.02, .2, .015, mat(0xc02020, { metal: .1 }));
    needle.position.set(0, 1.62, .08); g.add(needle);
    var ang = 2.4;
    return { group: g, anim: function (on, t, dt) {
      var target = on ? -.8 : 2.4;
      ang += (target - ang) * Math.min(1, dt * 2);
      needle.rotation.z = ang;
      needle.position.set(Math.sin(ang) * .085, 1.55 + Math.cos(ang) * .085, .08);
    } };
  }
  function bInput(d) {
    var g = new T.Group();
    var ped = box(.36, .85, .3, mat(0x222831, { rough: .45, metal: .4 })); ped.position.y = .42; g.add(ped);
    var face = box(.3, .34, .03, mat(0x10151d, { rough: .35 })); face.position.set(0, .68, .16); g.add(face);
    var capCol = d.kind === "estop" ? COL.red
      : d.kind === "button" ? COL.on
      : d.kind === "fault" ? COL.amber : COL.blue;
    var cap;
    if (d.kind === "estop") {
      var ring2 = cyl(.13, .13, .03, mat(COL.safety, { rough: .5 }));
      ring2.rotation.x = Math.PI / 2; ring2.position.set(0, .72, .18); g.add(ring2);
      cap = cyl(.09, .1, .08, mat(capCol, { emissive: capCol, ei: .1 }));
      cap.rotation.x = Math.PI / 2;
    } else {
      cap = new T.Mesh(new T.SphereGeometry(.07, 14, 10), mat(capCol, { emissive: capCol, ei: .1 }));
    }
    cap.position.set(0, .72, .2); g.add(cap);
    var led = box(.06, .06, .02, mat(COL.on, { emissive: COL.on, ei: 0 }));
    led.position.set(.1, .58, .18); g.add(led);
    return { group: g, anim: function (on, t) {
      cap.material.emissiveIntensity = on ? 1.7 : .1;
      led.material.emissiveIntensity = on ? 1.7 : (Math.sin(t * 3) > .85 ? .7 : 0);
    } };
  }
  function bFiller(d, ctx) {
    var g = new T.Group();
    [-0.55, 0.55].forEach(function (x) {
      var post = box(.13, 1.8, .13, mat(COL.frame, { metal: .55 })); post.position.set(x, .9, 0); g.add(post);
    });
    var beam = box(1.25, .16, .34, mat(COL.frame, { metal: .55 })); beam.position.y = 1.8; g.add(beam);
    var head = box(.56, .26, .3, mat(COL.blue, { metal: .55, rough: .3 })); head.position.y = 1.56; g.add(head);
    var nozzles = [];
    [-0.14, 0.14].forEach(function (x) {
      var noz = cyl(.035, .022, .3, mat(0xd9e2ec, { metal: .8, rough: .2 }));
      noz.position.set(x, 1.34, 0); g.add(noz); nozzles.push(noz);
    });
    var drop = new T.Mesh(new T.SphereGeometry(.045, 8, 8), mat(COL.water, { emissive: COL.water, ei: .9 }));
    drop.visible = false; g.add(drop);
    if (!(ctx && ctx.line)) {
      var bottle = cyl(.1, .1, .32, mat(COL.glass, { alpha: .5, rough: .12 }));
      bottle.position.y = .68; g.add(bottle);
    }
    return { group: g, anim: function (on, t) {
      var dip = on ? (Math.sin(t * 3) * .5 + .5) * .16 : 0;
      nozzles.forEach(function (n) { n.position.y = 1.34 - dip; });
      drop.visible = !!on && Math.sin(t * 3) > 0;
      if (drop.visible) drop.position.set(.0, 1.1 - ((t * 1.8) % 1) * .25, 0);
    } };
  }
  function bCapper(d, ctx) {
    var g = new T.Group();
    [-0.5, 0.5].forEach(function (x) {
      var post = box(.13, 1.7, .13, mat(COL.frame, { metal: .55 })); post.position.set(x, .85, 0); g.add(post);
    });
    var beam = box(1.15, .16, .34, mat(COL.frame, { metal: .55 })); beam.position.y = 1.7; g.add(beam);
    var ram = box(.32, .46, .28, mat(COL.safety, { metal: .35, rough: .45 })); ram.position.y = 1.35; g.add(ram);
    var chuck = cyl(.12, .12, .12, mat(COL.steelDark, { metal: .7 })); chuck.position.y = 1.06; g.add(chuck);
    if (!(ctx && ctx.line)) {
      var bottle = cyl(.1, .1, .32, mat(COL.glass, { alpha: .5, rough: .12 }));
      bottle.position.y = .68; g.add(bottle);
    }
    return { group: g, anim: function (on, t) {
      var press = on ? Math.max(0, Math.sin(t * 4)) * .2 : 0;
      ram.position.y = 1.35 - press; chuck.position.y = 1.06 - press;
    } };
  }

  // 6축 느낌의 다관절 로봇 — 베이스 선회 + 어깨/팔꿈치/손목 + 그리퍼 픽사이클
  function bRobot() {
    var g = new T.Group();
    var base = cyl(.34, .42, .26, mat(COL.safety, { rough: .45, metal: .35 }));
    base.position.y = .13; g.add(base);
    var yaw = new T.Group(); yaw.position.y = .26; g.add(yaw);
    var turret = cyl(.26, .3, .3, mat(0xd8dde4, { metal: .4, rough: .35 }));
    turret.position.y = .15; yaw.add(turret);
    var shoulder = new T.Group(); shoulder.position.y = .32; yaw.add(shoulder);
    var upper = box(.2, .85, .26, mat(0xe8ebef, { metal: .4, rough: .3 }));
    upper.position.y = .42; shoulder.add(upper);
    var elbow = new T.Group(); elbow.position.y = .85; shoulder.add(elbow);
    var fore = box(.16, .7, .2, mat(0xd8dde4, { metal: .4, rough: .3 }));
    fore.position.y = .35; elbow.add(fore);
    var wrist = new T.Group(); wrist.position.y = .7; elbow.add(wrist);
    var hand = box(.14, .18, .14, mat(COL.steelDark, { metal: .6 }));
    hand.position.y = .09; wrist.add(hand);
    [-0.05, 0.05].forEach(function (dx) {
      var fing = box(.03, .14, .08, mat(0x222831, { metal: .5 }));
      fing.position.set(dx, .25, 0); wrist.add(fing);
    });
    [shoulder, elbow].forEach(function (j) {
      var jc = cyl(.12, .12, .3, mat(COL.safety, { rough: .45, metal: .35 }));
      jc.rotation.z = Math.PI / 2; j.add(jc);
    });
    var led = box(.07, .07, .03, mat(COL.on, { emissive: COL.on, ei: .1 }));
    led.position.set(0, .3, .31); yaw.add(led);
    return { group: g, anim: function (on, t, dt) {
      var s = on ? Math.sin(t * 1.6) : 0;           // 픽&플레이스 사이클
      yaw.rotation.y += ((on ? Math.sin(t * .8) * 1.1 : 0) - yaw.rotation.y) * Math.min(1, dt * 3);
      shoulder.rotation.x = -.5 + (on ? s * .45 : 0);
      elbow.rotation.x = .95 + (on ? -s * .7 : 0);
      wrist.rotation.x = -.45 + (on ? s * .3 : 0);
      led.material.emissiveIntensity = on ? 1.6 : .1;
    } };
  }
  // 비전 카메라 — 마스트 + 카메라 헤드 + 검사 빔(스캔)
  function bVision() {
    var g = new T.Group();
    var mast = cyl(.05, .07, 1.7, mat(COL.frame, { metal: .55 })); mast.position.y = .85; g.add(mast);
    var arm = box(.5, .08, .08, mat(COL.frame, { metal: .55 })); arm.position.set(.22, 1.66, 0); g.add(arm);
    var cam = box(.22, .16, .3, mat(0x1b2129, { metal: .45, rough: .3 }));
    cam.position.set(.45, 1.6, 0); g.add(cam);
    var lens = cyl(.05, .06, .08, mat(0x0a0e13, { metal: .2, rough: .2 }));
    lens.rotation.x = Math.PI / 2; lens.position.set(.45, 1.5, .0); g.add(lens);
    var ring = torus(.07, .012, mat(0xff3838, { emissive: 0xff3838, ei: .2 }));
    ring.rotation.x = Math.PI / 2; ring.position.set(.45, 1.49, 0); g.add(ring);
    var beam = new T.Mesh(new T.ConeGeometry(.34, 1.1, 20, 1, true),
      mat(0xff4040, { emissive: 0xff3030, ei: .5, alpha: .12, side: T.DoubleSide }));
    beam.position.set(.45, .95, 0); g.add(beam);
    return { group: g, anim: function (on, t) {
      beam.visible = !!on;
      ring.material.emissiveIntensity = on ? 1.8 : .2;
      if (on) beam.scale.x = beam.scale.z = 1 + Math.sin(t * 6) * .12;
    } };
  }

  var BUILDERS = {
    motor: bMotor, pump: bPump, valve: bValve, heater: bHeater, cooler: bFan,
    fan: bFan, conveyor: bConveyor, beacon: bBeacon, ejector: bEjector,
    gate: bGate, mixer: bMixer, actuator: bActuator, tank: bTank, gauge: bGauge,
    filler: bFiller, capper: bCapper, labeler: bMixer, washer: bFan, packer: bActuator,
    robot: bRobot, vision: bVision,
    button: bInput, estop: bInput, level: bInput, fault: bInput, sensor: bInput,
  };

  // 공유 이송 라인(스파인) — 스테이션 기기들을 하나의 컨베이어로 물리적으로 잇는다.
  var LINE_KINDS = ["conveyor", "filler", "capper", "labeler", "washer", "packer",
    "ejector", "robot"];
  function buildLine(scene, lineDevs) {
    var xs = lineDevs.map(function (d) { return d.x; });
    var x0 = Math.min.apply(null, xs) - 1.5, x1 = Math.max.apply(null, xs) + 1.5;
    var z = lineDevs[0].z, len = x1 - x0, cx = (x0 + x1) / 2;
    var g = new T.Group();
    [-0.34, 0.34].forEach(function (dz) {                       // 사이드 프레임
      var fr = box(len, .14, .04, mat(COL.blueDeep, { metal: .55, rough: .35 }));
      fr.position.set(cx, .6, z + dz); g.add(fr);
    });
    var belt = box(len - .1, .035, .6, mat(0x171b21, { rough: .85, metal: .1 }));
    belt.position.set(cx, .62, z); g.add(belt);
    for (var lx = x0 + .6; lx < x1 - .3; lx += 1.2) {            // 다리
      [-0.26, 0.26].forEach(function (dz) {
        var leg = box(.07, .56, .07, mat(COL.frame, { metal: .5 }));
        leg.position.set(lx, .28, z + dz); g.add(leg);
      });
    }
    var items = [];
    var n = Math.max(5, Math.floor(len / .9));
    for (var i = 0; i < n; i++) {                                // 라인 전체를 흐르는 제품
      var it = cyl(.085, .085, .26, mat(COL.glass, { alpha: .55, rough: .15, metal: .1 }));
      var cap = cyl(.05, .05, .05, mat(COL.blue, { metal: .4 })); cap.position.y = .155; it.add(cap);
      it.position.set(x0 + .4 + i * (len - .8) / n, .78, z); g.add(it);
      it.userData = { ej: false, vz: 0, vy: 0, passed: false };
      items.push(it);
    }
    // 배출 슈트(ejector 위치 옆 경사판) — 밀려난 제품이 떨어지는 곳
    var ejDev = lineDevs.filter(function (d) { return d.kind === "ejector"; })[0];
    var ejX = ejDev ? ejDev.x : null;
    if (ejX != null) {
      var chute = box(.5, .02, .6, mat(COL.steelDark, { metal: .55, rough: .4 }));
      chute.position.set(ejX, .5, z + .8); chute.rotation.x = -0.5; g.add(chute);
    }
    scene.add(g);
    return { x0: x0 + .3, x1: x1 - .3, z: z, ejX: ejX, baseY: .78, items: items };
  }

  function deviceOn(d, r) {
    if (!r) return false;
    if (d.role === "output") return !!r.outputs[d.symbol];
    if (d.role === "input") return !!r.inputs[d.symbol];
    if (d.role === "tank") {
      for (var i = 0; i < d.fed_by.length; i++)
        if (r.outputs[d.fed_by[i]]) return true;
      return false;
    }
    if (d.role === "gauge") {
      for (var k in r.inputs)
        if (k.indexOf(d.symbol + "_") === 0 && r.inputs[k]) return true;
      return false;
    }
    return false;
  }

  // ── 공장 환경 — 바닥(콘크리트)·통로(체커)·위험띠·I빔 구조·가드레일·캐비닛 ──
  function buildEnvironment(scene, fw, fd, plcPos) {
    var floor = new T.Mesh(new T.PlaneGeometry(fw + 12, fd + 12),
      mat(0xffffff, { rough: .85, metal: .08, map: texConcrete(), envI: .5 }));
    floor.rotation.x = -Math.PI / 2; floor.receiveShadow = true; scene.add(floor);
    // 통로(체커플레이트) — 조작반 앞
    var walk = new T.Mesh(new T.PlaneGeometry(fw + 4, 1.4),
      mat(0xffffff, { rough: .5, metal: .55, map: texChecker(), envI: .8 }));
    walk.rotation.x = -Math.PI / 2; walk.position.set(0, .012, 4.1); walk.receiveShadow = true;
    scene.add(walk);
    // 위험띠 — 설비 존 둘레
    var hz = texHazard();
    [[0, -(fd + 1.6) / 2, fw + 5, .22, 0], [0, (fd - 1.4) / 2, fw + 5, .22, 0],
     [-(fw + 5) / 2, -.85, .22, fd - .2, 1], [(fw + 5) / 2, -.85, .22, fd - .2, 1]]
    .forEach(function (st) {
      var m2 = mat(0xffffff, { rough: .6, metal: .1, map: hz });
      var ln = new T.Mesh(new T.PlaneGeometry(st[2], st[3]), m2);
      ln.rotation.x = -Math.PI / 2; if (st[4]) ln.rotation.z = Math.PI / 2;
      ln.position.set(st[0], .015, st[1]); scene.add(ln);
    });
    // I빔 기둥 + 보 + 트러스 느낌의 보조 부재
    var H = 4.6, px = (fw + 9) / 2, pz = (fd + 7) / 2;
    var beamMat = mat(COL.frame, { metal: .6, rough: .42 });
    [[-px, -pz], [px, -pz], [-px, pz], [px, pz]].forEach(function (p2) {
      var col = iBeam(H, .3, beamMat);
      col.position.set(p2[0], H, p2[1]); scene.add(col);
      var foot = box(.5, .06, .5, beamMat); foot.position.set(p2[0], .03, p2[1]); scene.add(foot);
    });
    [-pz, pz].forEach(function (z2) {
      var beam = iBeam(px * 2, .26, beamMat, true);
      beam.position.set(-px, H - .15, z2); scene.add(beam);
    });
    // 천장 조명 기구(발광 패널) — PMREM 환경과 함께 금속 하이라이트를 만든다
    for (var lx = -px + 2; lx <= px - 2; lx += 4) {
      var fix = box(1.6, .06, .4, mat(0xeef4fb, { emissive: 0xdfe9f5, ei: .9, metal: 0, rough: 1 }));
      fix.position.set(lx, H - .35, 0); fix.castShadow = false; scene.add(fix);
    }
    // 가드레일(설비 존 뒤)
    var railZ = -(fd + .4) / 2;
    for (var rx2 = -fw / 2; rx2 <= fw / 2 + .01; rx2 += 2) {
      var post2 = cyl(.045, .045, 1.1, mat(COL.safety, { rough: .5, metal: .3 }));
      post2.position.set(rx2, .55, railZ); scene.add(post2);
    }
    [0.55, 0.95].forEach(function (ry) {
      var rail = cyl(.03, .03, fw + .2, mat(COL.safety, { rough: .5, metal: .3 }));
      rail.rotation.z = Math.PI / 2; rail.position.set(0, ry, railZ); scene.add(rail);
    });
    // PLC 제어반 캐비닛
    var cab = new T.Group();
    var bodyC = box(1.1, 2, .6, mat(COL.cabinet, { metal: .4, rough: .35 }));
    bodyC.position.y = 1; cab.add(bodyC);
    var door = box(1, 1.8, .04, mat(0x47699c, { metal: .35, rough: .3 }));
    door.position.set(0, 1, .32); cab.add(door);
    var handle = box(.04, .3, .05, mat(0xd9e2ec, { metal: .8, rough: .2 }));
    handle.position.set(.4, 1, .36); cab.add(handle);
    var vent = box(.6, .26, .02, mat(0x2c4368, { rough: .7 }));
    vent.position.set(0, .4, .345); cab.add(vent);
    var leds = [];
    for (var i2 = 0; i2 < 3; i2++) {
      var led = box(.07, .07, .03, mat([COL.on, COL.amber, COL.blue][i2],
        { emissive: [COL.on, COL.amber, COL.blue][i2], ei: .4 }));
      led.position.set(-.3 + i2 * .3, 1.7, .35); cab.add(led); leds.push(led);
    }
    var cabLabel = labelSprite("PLC", "LS XGK");
    cabLabel.position.set(0, 2.45, 0);
    cab.add(cabLabel);
    cab.position.set(plcPos.x, 0, plcPos.z);
    scene.add(cab);
    // 배전반(MDB) — 수배전 캐비닛: 인입 차단기 + 분기 차단기 핸들 행렬
    var mdb = new T.Group();
    var mbody = box(1.2, 2.1, .6, mat(0x44505e, { metal: .4, rough: .35 }));
    mbody.position.y = 1.05; mdb.add(mbody);
    var mdoor = box(1.1, 1.9, .04, mat(0x53616f, { metal: .35, rough: .3 }));
    mdoor.position.set(0, 1.05, .32); mdb.add(mdoor);
    var main = box(.34, .42, .06, mat(0x20262e, { rough: .4 }));
    main.position.set(0, 1.72, .34); mdb.add(main);
    var mhandle = box(.07, .2, .05, mat(0xd6a416, { rough: .4, metal: .3 }));
    mhandle.position.set(0, 1.72, .39); mdb.add(mhandle);
    for (var bi2 = 0; bi2 < 6; bi2++) {
      var br = box(.22, .3, .05, mat(0x20262e, { rough: .4 }));
      br.position.set(-.38 + (bi2 % 3) * .38, 1.2 - Math.floor(bi2 / 3) * .42, .34);
      mdb.add(br);
      var bh = box(.05, .14, .04, mat(0x9aa8b8, { metal: .5 }));
      bh.position.set(-.38 + (bi2 % 3) * .38, 1.2 - Math.floor(bi2 / 3) * .42, .38);
      mdb.add(bh);
    }
    var mdbLabel = labelSprite("MDB", "수배전반 3Φ 380V");
    mdbLabel.position.set(0, 2.55, 0);
    mdb.add(mdbLabel);
    mdb.position.set(plcPos.x + 1.6, 0, plcPos.z);
    scene.add(mdb);
    // 케이블 트레이(바닥, 캐비닛까지)
    var trayLen = Math.abs(plcPos.x) + fw / 2;
    var tray = new T.Group();
    var trayBase = box(trayLen, .03, .34, mat(COL.steelDark, { metal: .6, rough: .4 }));
    trayBase.position.set(plcPos.x - trayLen / 2, .05, plcPos.z + .9); tray.add(trayBase);
    [-0.17, 0.17].forEach(function (dz) {
      var wall = box(trayLen, .1, .02, mat(COL.steelDark, { metal: .6, rough: .4 }));
      wall.position.set(plcPos.x - trayLen / 2, .1, plcPos.z + .9 + dz); tray.add(wall);
    });
    scene.add(tray);
    return { leds: leds, pos: new T.Vector3(plcPos.x, 1.1, plcPos.z) };
  }

  function buildPipe(scene, a, b) {
    var top = Math.max(a.y, b.y) + 1;
    var pts = [
      new T.Vector3(a.x, a.y, a.z),
      new T.Vector3(a.x, top, a.z),
      new T.Vector3(b.x, top, b.z),
      new T.Vector3(b.x, b.y, b.z),
    ];
    var curve = flangedPipe(scene, pts, .07, mat(COL.pipe, { metal: .7, rough: .3 }));
    var drops = [];
    for (var i = 0; i < 6; i++) {
      var d = new T.Mesh(new T.SphereGeometry(.05, 8, 8),
        mat(COL.water, { emissive: COL.water, ei: .8 }));
      d.visible = false; scene.add(d); drops.push({ m: d, t: i / 6 });
    }
    return { curve: curve, drops: drops };
  }
  function buildCable(scene, a, b) {
    var pts = [
      new T.Vector3(a.x, .07, a.z),
      new T.Vector3(a.x, .07, (a.z + b.z) / 2 + .9),
      new T.Vector3(b.x, .07, (a.z + b.z) / 2 + .9),
      new T.Vector3(b.x, .07, b.z),
    ];
    var curve = new T.CatmullRomCurve3(pts, false, "catmullrom", .01);
    var m = mat(COL.cable, { metal: .25, rough: .7, emissive: COL.on, ei: 0 });
    var tube = new T.Mesh(new T.TubeGeometry(curve, 26, .024, 6), m);
    scene.add(tube);
    return m;
  }

  // 절차 환경맵 — RoomEnvironment 동급(외부 에셋 0) → PBR 금속 반사
  function makeEnvironment(renderer, scene) {
    try {
      var env = new T.Scene();
      env.background = new T.Color(0x10141a);
      var geo = new T.BoxGeometry(10, 10, 10);
      var room = new T.Mesh(geo, new T.MeshBasicMaterial({ color: 0x252c36, side: T.BackSide }));
      env.add(room);
      [[0, 4.5, 0, 4, 1.2], [-4, 2, 0, 1, 3], [4, 2, 2, 1, 3]].forEach(function (p) {
        var lp = new T.Mesh(new T.PlaneGeometry(p[3], p[4]),
          new T.MeshBasicMaterial({ color: 0xcfe2f8 }));
        lp.position.set(p[0], p[1], p[2]);
        if (p[1] > 4) lp.rotation.x = Math.PI / 2; else lp.lookAt(0, 1, 0);
        env.add(lp);
      });
      var pmrem = new T.PMREMGenerator(renderer);
      var envTex = pmrem.fromScene(env, .04).texture;
      scene.environment = envTex;
      pmrem.dispose();
    } catch (e) { /* 헤드리스/미지원 — 환경반사 없이 진행(치명 아님) */ }
  }

  function create(container, plant, opts) {
    var onToggle = (opts && opts.onToggle) || null;
    var W = container.clientWidth || 600, H = container.clientHeight || 360;
    var renderer = new T.WebGLRenderer({ antialias: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.setSize(W, H);
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = T.PCFSoftShadowMap;
    renderer.toneMapping = T.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.12;
    if ("outputColorSpace" in renderer) renderer.outputColorSpace = T.SRGBColorSpace;
    container.appendChild(renderer.domElement);
    var scene = new T.Scene();
    scene.background = new T.Color(0x0b0f15);
    scene.fog = new T.Fog(0x0b0f15, 22, 52);
    var cam = new T.PerspectiveCamera(44, W / H, .1, 140);

    makeEnvironment(renderer, scene);
    scene.add(new T.HemisphereLight(0xbfd2e8, 0x141a22, .5));
    var sun = new T.DirectionalLight(0xfff0dc, 2.2);
    sun.position.set(8, 13, 6);
    sun.castShadow = true;
    sun.shadow.mapSize.set(2048, 2048);
    sun.shadow.camera.left = -16; sun.shadow.camera.right = 16;
    sun.shadow.camera.top = 16; sun.shadow.camera.bottom = -16;
    sun.shadow.bias = -0.0004;
    scene.add(sun);
    var rim = new T.SpotLight(0x8fb8ff, 9, 40, Math.PI / 5, .55);
    rim.position.set(-8, 9, -6); scene.add(rim);

    var fw = Math.max(plant.floor_w, 10), fd = Math.max(plant.floor_d, 10);
    var plcEnv = buildEnvironment(scene, fw, fd, { x: fw / 2 + 2.6, z: 1.2 });

    var units = [], clickables = [];
    var posOf = {};
    // 공유 이송 라인 — 스테이션 기기 2대 이상이면 하나의 컨베이어로 잇는다(연결감)
    var lineDevs = (plant.devices || []).filter(function (d) {
      return d.role === "output" && LINE_KINDS.indexOf(d.kind) >= 0;
    }).sort(function (a, b) { return a.x - b.x; });
    var line = lineDevs.length >= 2 ? buildLine(scene, lineDevs) : null;
    var ctx = { line: !!line };
    (plant.devices || []).forEach(function (d) {
      var build = BUILDERS[d.kind] || bActuator;
      var u = build(d, ctx);
      u.dev = d;
      u.group.position.set(d.x, 0, d.z);
      var sp = labelSprite(d.tag || d.symbol, d.symbol);
      sp.position.set(0, d.kind === "tank" ? 3 : 2.05, 0);
      u.group.add(sp);
      scene.add(u.group);
      units.push(u);
      posOf[d.symbol] = new T.Vector3(d.x, d.kind === "tank" ? 2.5 : 1.05, d.z);
      if (d.role === "input" && onToggle) {
        u.group.traverse(function (o) { if (o.isMesh) { o.userData.sym = d.symbol; clickables.push(o); } });
      }
    });

    var pipes = [], cableMats = {};
    (plant.connections || []).forEach(function (c) {
      if (c.kind === "pipe" && posOf[c.src] && posOf[c.dst]) {
        pipes.push({ src: c.src, p: buildPipe(scene, posOf[c.src], posOf[c.dst]) });
      } else if (c.kind === "signal") {
        var dev = c.src === "PLC" ? c.dst : c.src;
        if (!posOf[dev]) return;
        cableMats[dev] = buildCable(scene, posOf[dev].clone().setY(0), plcEnv.pos.clone().setY(0));
      }
    });

    var theta = .85, phi = .92, dist = Math.max(fw, 11) * 1.12, auto = true;
    function placeCam() {
      cam.position.set(
        Math.sin(theta) * Math.cos(phi) * dist,
        Math.sin(phi) * dist * .56 + 1.5,
        Math.cos(theta) * Math.cos(phi) * dist);
      cam.lookAt(0, 1, 0);
    }
    placeCam();
    var el = renderer.domElement;
    el.style.touchAction = "none";
    var pointers = {}, moved = 0, pinchD = 0;
    el.addEventListener("pointerdown", function (e) {
      pointers[e.pointerId] = { x: e.clientX, y: e.clientY };
      auto = false; moved = 0;
      el.setPointerCapture(e.pointerId);
      var ids = Object.keys(pointers);
      if (ids.length === 2) {
        var a = pointers[ids[0]], b = pointers[ids[1]];
        pinchD = Math.hypot(a.x - b.x, a.y - b.y);
      }
    });
    el.addEventListener("pointermove", function (e) {
      var p = pointers[e.pointerId]; if (!p) return;
      var ids = Object.keys(pointers);
      if (ids.length === 2) {
        pointers[e.pointerId] = { x: e.clientX, y: e.clientY };
        var a = pointers[ids[0]], b = pointers[ids[1]];
        var nd = Math.hypot(a.x - b.x, a.y - b.y);
        if (pinchD > 0) dist = Math.max(5, Math.min(46, dist * pinchD / nd));
        pinchD = nd; placeCam(); return;
      }
      var dx = e.clientX - p.x, dy = e.clientY - p.y;
      moved += Math.abs(dx) + Math.abs(dy);
      theta -= dx * .006; phi = Math.max(.2, Math.min(1.35, phi + dy * .005));
      pointers[e.pointerId] = { x: e.clientX, y: e.clientY };
      placeCam();
    });
    function endPointer(e) {
      delete pointers[e.pointerId];
      pinchD = 0;
      if (moved < 6 && onToggle && clickables.length) {
        var rect = el.getBoundingClientRect();
        var v = new T.Vector2(
          ((e.clientX - rect.left) / rect.width) * 2 - 1,
          -((e.clientY - rect.top) / rect.height) * 2 + 1);
        var rc = new T.Raycaster(); rc.setFromCamera(v, cam);
        var hit = rc.intersectObjects(clickables, false)[0];
        if (hit && hit.object.userData.sym) onToggle(hit.object.userData.sym);
      }
    }
    el.addEventListener("pointerup", endPointer);
    el.addEventListener("pointercancel", endPointer);
    el.addEventListener("wheel", function (e) {
      e.preventDefault();
      dist = Math.max(5, Math.min(46, dist + e.deltaY * .012)); placeCam();
    }, { passive: false });

    var latest = null, clock = new T.Clock(), dead = false;
    function frame() {
      if (dead) return;
      requestAnimationFrame(frame);
      var dt = Math.min(clock.getDelta(), .12), t = clock.elapsedTime;
      if (auto) { theta += dt * .09; placeCam(); }
      units.forEach(function (u) { u.anim(deviceOn(u.dev, latest), t, dt); });
      pipes.forEach(function (pp) {
        var flowing = latest && latest.outputs[pp.src];
        pp.p.drops.forEach(function (dr) {
          dr.m.visible = !!flowing;
          if (flowing) {
            dr.t = (dr.t + dt * .32) % 1;
            pp.p.curve.getPointAt(dr.t, dr.m.position);
          }
        });
      });
      for (var s in cableMats) {
        var hot = latest && (latest.outputs[s] || latest.inputs[s]);
        cableMats[s].emissiveIntensity = hot ? .9 : 0;
      }
      plcEnv.leds.forEach(function (led, i) {
        led.material.emissiveIntensity = .3 + (Math.sin(t * (2 + i)) > 0 ? .9 : 0);
      });
      if (line) {                                   // 라인 물류 — 흐름 + 배출 서사
        var lineOn = !!latest && lineDevs.some(function (d) { return latest.outputs[d.symbol]; });
        var ejOn = !!latest && (latest.outputs.EJECT || latest.outputs.PUSHER ||
          (latest.table && latest.table.EJECT));
        line.items.forEach(function (it) {
          var u = it.userData;
          if (u.ej) {                               // 배출 중 — 옆으로 밀리며 낙하
            it.position.z += u.vz * dt; u.vy -= 6 * dt; it.position.y += u.vy * dt;
            it.rotation.x += dt * 4;
            if (it.position.y < -1) {               // 슈트 아래로 사라지면 입구로 재투입(양품화)
              u.ej = false; u.vy = 0; u.vz = 0; u.passed = false;
              it.position.set(line.x0, line.baseY, line.z); it.rotation.set(0, 0, 0);
              it.children.forEach(function (c) { if (c.material) c.material.color.set(COL.blue); });
            }
            return;
          }
          if (!lineOn) return;
          it.position.x += dt * 1.05;               // 라인 따라 이송
          // 배출기 통과 순간 EJECT 가 켜져 있으면 → 불량 판정·라인 밖으로 밀어냄
          if (line.ejX != null && !u.passed && it.position.x >= line.ejX) {
            u.passed = true;
            if (ejOn) {
              u.ej = true; u.vz = 1.6; u.vy = 1.2;  // 측면 푸시 + 살짝 튀어오름
              it.children.forEach(function (c) { if (c.material) c.material.color.set(COL.red); });
            }
          }
          if (it.position.x > line.x1) {            // 끝까지 간 양품 — 입구로 순환
            it.position.x = line.x0; u.passed = false;
          }
        });
      }
      renderer.render(scene, cam);
    }
    frame();

    return {
      update: function (r) { latest = r; },
      resize: function () {
        var w = container.clientWidth || W, h = container.clientHeight || H;
        cam.aspect = w / h; cam.updateProjectionMatrix(); renderer.setSize(w, h);
      },
      destroy: function () {
        dead = true;
        renderer.dispose();
        if (renderer.domElement.parentNode === container)
          container.removeChild(renderer.domElement);
      },
    };
  }

  window.Plant3D = { create: create };
})();
