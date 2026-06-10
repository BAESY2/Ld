/* plant3d.js — 3D 가상 공장 렌더러 v2 (Three.js, 서버 PlantLayout 기반).
 *
 * '진짜 공장' 문법으로 세운다: 콘크리트 바닥 + 안전 황색 구획선 + 철골 기둥/보,
 * PLC 제어반 캐비닛(상태 LED), 설비 간 **배관**(펌프→탱크, 흐름 입자 애니메이션)과
 * **제어 케이블 트레이**(기기↔PLC, 통전 시 발광)를 PlantLayout.connections 로 실제
 * 연결한다. 그림자·스포트라이트로 입체감, 검증된 ST 스캔(SimEngine)과 동기 가동.
 *
 * window.Plant3D.create(container, plant, {onToggle}) ->
 *   { update(simResult), resize(), destroy() }
 */
(function () {
  "use strict";
  if (!window.THREE) { window.Plant3D = null; return; }
  var T = window.THREE;

  var COL = {
    floor: 0x23262b, zone: 0x2e3138, line: 0xb89a2a, steel: 0x9aa6b4,
    dark: 0x3c4450, on: 0x3fb950, accent: 0x58a6ff, red: 0xff4d4d,
    amber: 0xd29922, water: 0x2f81f7, glass: 0xaec6dd, pipe: 0x8b97a6,
    cable: 0x20262e, cabinet: 0x36507a, concrete: 0x2a2d33,
  };

  function mat(color, opts) {
    var o = opts || {};
    return new T.MeshStandardMaterial({
      color: color, roughness: o.rough != null ? o.rough : .6,
      metalness: o.metal != null ? o.metal : .35,
      transparent: !!o.alpha, opacity: o.alpha || 1,
      emissive: o.emissive || 0x000000, emissiveIntensity: o.ei != null ? o.ei : 1,
    });
  }
  function box(w, h, d, m) { var x = new T.Mesh(new T.BoxGeometry(w, h, d), m); x.castShadow = true; return x; }
  function cyl(rt, rb, h, m, seg) {
    var x = new T.Mesh(new T.CylinderGeometry(rt, rb, h, seg || 24), m);
    x.castShadow = true; return x;
  }

  function labelSprite(text, sub) {
    var c = document.createElement("canvas");
    var ctx = c.getContext("2d");
    ctx.font = "700 30px system-ui, sans-serif";
    var w = Math.max(Math.ceil(ctx.measureText(text).width), sub ? ctx.measureText(sub).width * .66 : 0) + 30;
    var h = sub ? 64 : 46;
    c.width = w; c.height = h;
    ctx = c.getContext("2d");
    ctx.fillStyle = "rgba(8,13,20,.82)";
    ctx.beginPath();
    if (ctx.roundRect) ctx.roundRect(0, 0, w, h, 11); else ctx.rect(0, 0, w, h);
    ctx.fill();
    ctx.strokeStyle = "rgba(120,150,185,.4)"; ctx.stroke();
    ctx.fillStyle = "#dfeaf6"; ctx.font = "700 30px system-ui, sans-serif";
    ctx.fillText(text, 14, 33);
    if (sub) { ctx.fillStyle = "#7d8b9c"; ctx.font = "500 19px system-ui, sans-serif"; ctx.fillText(sub, 14, 55); }
    var sp = new T.Sprite(new T.SpriteMaterial({ map: new T.CanvasTexture(c), depthTest: false }));
    sp.scale.set(w / 120, h / 120, 1);
    return sp;
  }

  // ── 기기 빌더 — {group, anim(on, t, dt)} ──────────────────────────────────
  function bMotor() {
    var g = new T.Group();
    var base = box(1.15, .26, .85, mat(COL.concrete, { rough: .85 })); base.position.y = .13; g.add(base);
    var body = cyl(.36, .36, .85, mat(COL.accent, { metal: .55, rough: .35 }));
    body.rotation.z = Math.PI / 2; body.position.y = .6; g.add(body);
    // 냉각핀
    for (var i = -2; i <= 2; i++) {
      var fin = box(.62, .02, .78, mat(COL.dark, { metal: .6 }));
      fin.position.set(0, .6 + i * .1, 0); g.add(fin);
    }
    var ring = cyl(.38, .38, .1, mat(COL.dark, { emissive: COL.on, ei: 0 }));
    ring.rotation.z = Math.PI / 2; ring.position.set(-.42, .6, 0); g.add(ring);
    var shaft = cyl(.06, .06, .3, mat(COL.steel, { metal: .8 }));
    shaft.rotation.z = Math.PI / 2; shaft.position.set(.55, .6, 0); g.add(shaft);
    var rotor = new T.Group(); rotor.position.set(.72, .6, 0);
    for (var k = 0; k < 3; k++) {
      var bl = box(.05, .46, .12, mat(COL.steel, { metal: .4 }));
      bl.position.y = .22; var hold = new T.Group();
      hold.rotation.x = k * Math.PI * 2 / 3; hold.add(bl); rotor.add(hold);
    }
    rotor.rotation.z = Math.PI / 2; g.add(rotor);
    return { group: g, anim: function (on, t, dt) {
      if (on) rotor.rotateOnAxis(new T.Vector3(0, 1, 0), dt * 10);
      ring.material.emissiveIntensity = on ? 1.5 : 0;
    } };
  }
  function bPump() {
    var g = new T.Group();
    var base = box(1, .24, .9, mat(COL.concrete, { rough: .85 })); base.position.y = .12; g.add(base);
    var vol = cyl(.4, .46, .55, mat(COL.accent, { metal: .5, rough: .35 }));
    vol.position.y = .52; g.add(vol);
    var inlet = cyl(.13, .13, .5, mat(COL.pipe, { metal: .6 }));
    inlet.rotation.z = Math.PI / 2; inlet.position.set(-.55, .5, 0); g.add(inlet);
    var outlet = cyl(.13, .13, .55, mat(COL.pipe, { metal: .6 }));
    outlet.position.set(0, 1.05, 0); g.add(outlet);
    var m2 = cyl(.22, .22, .42, mat(COL.dark, { metal: .55 }));
    m2.rotation.z = Math.PI / 2; m2.position.set(.5, .52, 0); g.add(m2);
    var dome = new T.Mesh(new T.SphereGeometry(.18, 18, 12),
      mat(COL.on, { emissive: COL.on, ei: 0 }));
    dome.position.set(0, .86, 0); g.add(dome);
    return { group: g, anim: function (on, t) {
      var s = on ? 1 + Math.sin(t * 16) * .05 : 1;
      dome.scale.set(s, s, s);
      dome.material.emissiveIntensity = on ? 1.1 : 0;
    } };
  }
  function bValve() {
    var g = new T.Group();
    var pipe = cyl(.15, .15, 1.6, mat(COL.pipe, { metal: .6 }));
    pipe.rotation.z = Math.PI / 2; pipe.position.y = .5; g.add(pipe);
    var bodyV = box(.42, .4, .4, mat(COL.dark, { metal: .5 })); bodyV.position.y = .5; g.add(bodyV);
    var stem = cyl(.05, .05, .35, mat(COL.steel, { metal: .7 })); stem.position.y = .85; g.add(stem);
    var act = box(.42, .26, .3, mat(COL.accent, { metal: .4 })); act.position.y = 1.1; g.add(act);
    var wheel = new T.Mesh(new T.TorusGeometry(.24, .045, 10, 24),
      mat(COL.red, { emissive: COL.on, ei: 0 }));
    wheel.rotation.x = Math.PI / 2; wheel.position.y = 1.32; g.add(wheel);
    return { group: g, anim: function (on, t, dt) {
      if (on && wheel.rotation.z < Math.PI / 2) wheel.rotation.z += dt * 3;
      if (!on && wheel.rotation.z > 0) wheel.rotation.z -= dt * 3;
      wheel.material.color.set(on ? COL.on : COL.red);
      wheel.material.emissiveIntensity = on ? .9 : 0;
    } };
  }
  function bHeater() {
    var g = new T.Group();
    var body = box(1, 1.05, .85, mat(0x4a3a2c, { rough: .65 })); body.position.y = .55; g.add(body);
    var win = box(.7, .5, .03, mat(0x1a0f08, { rough: .3 })); win.position.set(0, .62, .44); g.add(win);
    var coil = box(.6, .4, .02, mat(0xff5a1f, { emissive: 0xff5a1f, ei: 0 }));
    coil.position.set(0, .62, .455); g.add(coil);
    var chimney = cyl(.09, .09, .5, mat(COL.pipe, { metal: .6 })); chimney.position.set(.3, 1.3, 0); g.add(chimney);
    return { group: g, anim: function (on, t) {
      coil.material.emissiveIntensity = on ? 1.7 + Math.sin(t * 7) * .4 : 0;
    } };
  }
  function bFan() {
    var g = new T.Group();
    var pole = cyl(.08, .1, 1.1, mat(COL.steel, { metal: .5 })); pole.position.y = .55; g.add(pole);
    var ringG = new T.Mesh(new T.TorusGeometry(.5, .045, 10, 28), mat(COL.dark, { metal: .5 }));
    ringG.position.y = 1.25; g.add(ringG);
    var hub = new T.Group(); hub.position.y = 1.25;
    for (var i = 0; i < 4; i++) {
      var bl = box(.08, .42, .16, mat(0x7fd2ff, { metal: .15 }));
      bl.position.y = .24; var hold = new T.Group();
      hold.rotation.z = i * Math.PI / 2; hold.add(bl); hub.add(hold);
    }
    g.add(hub);
    return { group: g, anim: function (on, t, dt) {
      if (on) hub.rotateOnAxis(new T.Vector3(0, 0, 1), dt * 11);
    } };
  }
  function bConveyor() {
    var g = new T.Group();
    var bed = box(2.4, .14, .8, mat(COL.dark, { metal: .45 })); bed.position.y = .58; g.add(bed);
    var belt = box(2.3, .04, .7, mat(0x14171c, { rough: .9 })); belt.position.y = .67; g.add(belt);
    [-1.05, 1.05].forEach(function (x) {
      var leg1 = box(.08, .58, .08, mat(COL.steel)); leg1.position.set(x, .29, .3); g.add(leg1);
      var leg2 = box(.08, .58, .08, mat(COL.steel)); leg2.position.set(x, .29, -.3); g.add(leg2);
      var roll = cyl(.09, .09, .76, mat(COL.steel, { metal: .6 }));
      roll.rotation.x = Math.PI / 2; roll.position.set(x, .6, 0); g.add(roll);
    });
    var items = [];
    for (var i = 0; i < 4; i++) {
      var it = box(.28, .24, .28, mat(COL.amber, { rough: .8, metal: .05 }));
      it.position.set(-1.05 + i * .62, .82, 0); g.add(it); items.push(it);
    }
    return { group: g, anim: function (on, t, dt) {
      if (!on) return;
      items.forEach(function (it) {
        it.position.x += dt * 1.1;
        if (it.position.x > 1.15) it.position.x = -1.15;
      });
    } };
  }
  function bBeacon() {
    var g = new T.Group();
    var pole = cyl(.05, .07, 1.5, mat(COL.steel, { metal: .5 })); pole.position.y = .75; g.add(pole);
    var cage = cyl(.13, .13, .3, mat(COL.dark)); cage.position.y = 1.55; g.add(cage);
    var lamp = cyl(.11, .11, .26, mat(COL.red, { emissive: COL.red, ei: 0, alpha: .95 }));
    lamp.position.y = 1.56; g.add(lamp);
    var light = new T.PointLight(COL.red, 0, 7); light.position.y = 1.6; g.add(light);
    return { group: g, anim: function (on, t) {
      var f = on ? (Math.sin(t * 11) > 0 ? 2 : .12) : 0;
      lamp.material.emissiveIntensity = f; light.intensity = f * 1.4;
    } };
  }
  function bEjector() {
    var g = new T.Group();
    var base = box(.55, .5, .55, mat(COL.dark, { metal: .45 })); base.position.y = .3; g.add(base);
    var cylBody = cyl(.12, .12, .5, mat(COL.accent, { metal: .5 }));
    cylBody.rotation.x = Math.PI / 2; cylBody.position.set(0, .45, .35); g.add(cylBody);
    var rod = cyl(.05, .05, .6, mat(COL.steel, { metal: .8 }));
    rod.rotation.x = Math.PI / 2; rod.position.set(0, .45, .75); g.add(rod);
    var head = box(.42, .42, .1, mat(COL.amber)); head.position.set(0, .45, 1.05); g.add(head);
    return { group: g, anim: function (on, t, dt) {
      var target = on ? 1.45 : 1.05;
      head.position.z += (target - head.position.z) * Math.min(1, dt * 8);
      rod.position.z = (head.position.z + .45) / 2 - .12;
      rod.scale.y = (head.position.z - .55) / .5;
    } };
  }
  function bGate() {
    var g = new T.Group();
    [-0.6, 0.6].forEach(function (x) {
      var post = box(.14, 1.5, .14, mat(COL.line, { rough: .6 })); post.position.set(x, .75, 0); g.add(post);
    });
    var beam = box(1.34, .12, .14, mat(COL.line, { rough: .6 })); beam.position.y = 1.5; g.add(beam);
    var panel = box(1.06, 1, .06, mat(COL.steel, { metal: .55, alpha: .92 })); panel.position.y = .55; g.add(panel);
    return { group: g, anim: function (on, t, dt) {
      var target = on ? 1.28 : .55;
      panel.position.y += (target - panel.position.y) * Math.min(1, dt * 6);
    } };
  }
  function bMixer() {
    var g = new T.Group();
    var vessel = cyl(.5, .4, .95, mat(COL.glass, { alpha: .35, rough: .15, metal: .1 }));
    vessel.position.y = .55; g.add(vessel);
    var top = box(.5, .12, .5, mat(COL.dark, { metal: .5 })); top.position.y = 1.12; g.add(top);
    var m3 = cyl(.16, .16, .3, mat(COL.accent, { metal: .5 })); m3.position.y = 1.35; g.add(m3);
    var shaft = new T.Group(); shaft.position.y = .6;
    var rodS = cyl(.035, .035, .9, mat(COL.steel, { metal: .7 })); rodS.position.y = .2; shaft.add(rodS);
    var blade = box(.62, .07, .1, mat(COL.steel, { metal: .7 })); blade.position.y = -.2; shaft.add(blade);
    g.add(shaft);
    return { group: g, anim: function (on, t, dt) {
      if (on) shaft.rotateOnAxis(new T.Vector3(0, 1, 0), dt * 8);
    } };
  }
  function bActuator() {
    var g = new T.Group();
    var body = box(.75, .75, .75, mat(COL.dark, { emissive: COL.on, ei: 0 }));
    body.position.y = .38; g.add(body);
    return { group: g, anim: function (on) { body.material.emissiveIntensity = on ? .85 : 0; } };
  }
  function bTank() {
    var g = new T.Group();
    [-0.5, 0.5].forEach(function (x) {
      var leg = box(.1, .5, .1, mat(COL.steel, { metal: .5 })); leg.position.set(x * .9, .25, 0); g.add(leg);
    });
    var shell = cyl(.68, .68, 1.7, mat(COL.glass, { alpha: .25, rough: .12, metal: .15 }));
    shell.position.y = 1.3; shell.castShadow = false; g.add(shell);
    var cap = new T.Mesh(new T.SphereGeometry(.68, 24, 10, 0, Math.PI * 2, 0, Math.PI / 2),
      mat(COL.steel, { metal: .5, rough: .4 }));
    cap.position.y = 2.15; g.add(cap);
    var water = cyl(.62, .62, 1, mat(COL.water, { alpha: .8, rough: .25, metal: 0 }));
    water.position.y = .85; water.scale.y = .35; water.castShadow = false; g.add(water);
    var inlet = cyl(.1, .1, .45, mat(COL.pipe, { metal: .6 }));
    inlet.position.set(0, 2.35, 0); g.add(inlet);
    [.7, 1.95].forEach(function (y) {
      var markL = new T.Mesh(new T.TorusGeometry(.69, .015, 6, 32), mat(COL.amber, { emissive: COL.amber, ei: .4 }));
      markL.rotation.x = Math.PI / 2; markL.position.y = y; g.add(markL);
    });
    var level = .35;
    return { group: g, anim: function (on, t, dt) {
      level = Math.max(.06, Math.min(.95, level + (on ? .1 : -.045) * dt));
      water.scale.y = level;
      water.position.y = .5 + level * 1.6 / 2 + .05;
    } };
  }
  function bGauge() {
    var g = new T.Group();
    var pole = box(.1, 1.25, .1, mat(COL.steel, { metal: .5 })); pole.position.y = .62; g.add(pole);
    var panel = box(.62, .92, .1, mat(0x10161f, { rough: .35 })); panel.position.y = 1.5; g.add(panel);
    var bar = box(.15, .8, .04, mat(COL.on, { emissive: COL.on, ei: .5 }));
    bar.position.set(-.13, 1.5, .08); bar.scale.y = .12; g.add(bar);
    var mark = box(.3, .03, .05, mat(COL.amber, { emissive: COL.amber, ei: .8 }));
    mark.position.set(.12, 1.5, .08); g.add(mark);
    var lvl = .12;
    return { group: g, anim: function (on, t, dt) {
      var target = on ? .85 : .12;
      lvl += (target - lvl) * Math.min(1, dt * 2.2);
      bar.scale.y = lvl;
      bar.position.y = 1.5 - .4 + lvl * .4;
      bar.material.color.set(on ? COL.red : COL.on);
      bar.material.emissive.set(on ? COL.red : COL.on);
    } };
  }
  function bInput(d) {
    var g = new T.Group();
    var ped = box(.34, .78, .3, mat(0x1a2027, { rough: .5, metal: .35 })); ped.position.y = .39; g.add(ped);
    var face = box(.28, .3, .03, mat(0x10161f)); face.position.set(0, .62, .16); g.add(face);
    var capCol = d.kind === "estop" ? COL.red
      : d.kind === "button" ? COL.on
      : d.kind === "fault" ? COL.amber : COL.accent;
    var capGeo = d.kind === "estop"
      ? new T.CylinderGeometry(.1, .1, .07, 18)
      : new T.SphereGeometry(.075, 14, 10);
    var cap = new T.Mesh(capGeo, mat(capCol, { emissive: capCol, ei: 0 }));
    if (d.kind === "estop") cap.rotation.x = Math.PI / 2;
    cap.position.set(0, .66, .19); g.add(cap);
    var led = box(.05, .05, .02, mat(COL.on, { emissive: COL.on, ei: 0 }));
    led.position.set(.09, .54, .18); g.add(led);
    return { group: g, anim: function (on, t) {
      cap.material.emissiveIntensity = on ? 1.6 : 0;
      led.material.emissiveIntensity = on ? 1.6 : (Math.sin(t * 3) > .85 ? .6 : 0);
    } };
  }

  // 보틀링 라인 — 충전기(겐트리+노즐 하강·적하), 캡핑기(프레스 헤드 스탬핑)
  function bFiller() {
    var g = new T.Group();
    [-0.5, 0.5].forEach(function (x) {
      var post = box(.12, 1.7, .12, mat(COL.steel, { metal: .5 })); post.position.set(x, .85, 0); g.add(post);
    });
    var beam = box(1.15, .14, .3, mat(COL.steel, { metal: .5 })); beam.position.y = 1.7; g.add(beam);
    var head = box(.5, .22, .26, mat(COL.accent, { metal: .4 })); head.position.y = 1.5; g.add(head);
    var noz = cyl(.045, .03, .3, mat(COL.steel, { metal: .7 })); noz.position.y = 1.3; g.add(noz);
    var drop = new T.Mesh(new T.SphereGeometry(.05, 8, 8),
      mat(COL.water, { emissive: COL.water, ei: .8 }));
    drop.position.y = 1.0; drop.visible = false; g.add(drop);
    var bottle = cyl(.11, .11, .34, mat(COL.glass, { alpha: .4, rough: .15 }));
    bottle.position.y = .65; g.add(bottle);
    var t0 = 0;
    return { group: g, anim: function (on, t, dt) {
      t0 = t;
      var dip = on ? (Math.sin(t * 3) * .5 + .5) * .18 : 0;   // 노즐 주기 하강
      head.position.y = 1.5 - dip; noz.position.y = 1.3 - dip;
      drop.visible = !!on && Math.sin(t * 3) > 0;
      if (drop.visible) drop.position.y = 1.05 - ((t * 1.7) % 1) * .25;
    } };
  }
  function bCapper() {
    var g = new T.Group();
    [-0.45, 0.45].forEach(function (x) {
      var post = box(.12, 1.6, .12, mat(COL.steel, { metal: .5 })); post.position.set(x, .8, 0); g.add(post);
    });
    var beam = box(1.05, .14, .3, mat(COL.steel, { metal: .5 })); beam.position.y = 1.6; g.add(beam);
    var ram = box(.3, .42, .26, mat(COL.amber, { metal: .35 })); ram.position.y = 1.28; g.add(ram);
    var chuck = cyl(.13, .13, .12, mat(COL.dark, { metal: .6 })); chuck.position.y = 1.02; g.add(chuck);
    var bottle = cyl(.11, .11, .34, mat(COL.glass, { alpha: .4, rough: .15 }));
    bottle.position.y = .65; g.add(bottle);
    return { group: g, anim: function (on, t) {
      var press = on ? Math.max(0, Math.sin(t * 4)) * .2 : 0;   // 스탬핑
      ram.position.y = 1.28 - press; chuck.position.y = 1.02 - press;
    } };
  }

  var BUILDERS = {
    motor: bMotor, pump: bPump, valve: bValve, heater: bHeater, cooler: bFan,
    fan: bFan, conveyor: bConveyor, beacon: bBeacon, ejector: bEjector,
    gate: bGate, mixer: bMixer, actuator: bActuator, tank: bTank, gauge: bGauge,
    filler: bFiller, capper: bCapper, labeler: bMixer, washer: bFan, packer: bActuator,
    button: bInput, estop: bInput, level: bInput, fault: bInput, sensor: bInput,
  };

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

  // ── 공장 환경(바닥·구획선·기둥·보·캐비닛) ────────────────────────────────
  function buildEnvironment(scene, fw, fd, plcPos) {
    var floor = new T.Mesh(new T.PlaneGeometry(fw + 10, fd + 10),
      mat(COL.floor, { rough: .92, metal: .04 }));
    floor.rotation.x = -Math.PI / 2; floor.receiveShadow = true; scene.add(floor);
    // 설비 구획(어두운 존) + 안전 황색 라인
    var zone = new T.Mesh(new T.PlaneGeometry(fw + 4, fd + 2), mat(COL.zone, { rough: .9 }));
    zone.rotation.x = -Math.PI / 2; zone.position.y = .005; zone.receiveShadow = true; scene.add(zone);
    var ring = [
      [-(fw + 4) / 2, -(fd + 2) / 2, fw + 4, .14], [-(fw + 4) / 2, (fd + 2) / 2 - .14, fw + 4, .14],
    ];
    ring.forEach(function (rr) {
      var ln = new T.Mesh(new T.PlaneGeometry(rr[2], rr[3]), mat(COL.line, { rough: .6, ei: .15, emissive: COL.line }));
      ln.rotation.x = -Math.PI / 2; ln.position.set(rr[0] + rr[2] / 2, .01, rr[1] + rr[3] / 2); scene.add(ln);
    });
    [[-(fw + 4) / 2, 0], [(fw + 4) / 2 - .14, 0]].forEach(function (p2) {
      var ln = new T.Mesh(new T.PlaneGeometry(.14, fd + 2), mat(COL.line, { rough: .6, ei: .15, emissive: COL.line }));
      ln.rotation.x = -Math.PI / 2; ln.position.set(p2[0] + .07, .01, p2[1]); scene.add(ln);
    });
    // 철골 기둥 + 상부 보
    var px = (fw + 8) / 2, pz = (fd + 6) / 2, H = 4.2;
    [[-px, -pz], [px, -pz], [-px, pz], [px, pz]].forEach(function (p2) {
      var col = box(.22, H, .22, mat(COL.steel, { metal: .5, rough: .5 }));
      col.position.set(p2[0], H / 2, p2[1]); scene.add(col);
    });
    [[-pz, 0], [pz, 0]].forEach(function (z2, i) {
      var beam = box(px * 2 + .2, .18, .18, mat(COL.steel, { metal: .5 }));
      beam.position.set(0, H, i === 0 ? -pz : pz); scene.add(beam);
    });
    // PLC 제어반 캐비닛
    var cab = new T.Group();
    var bodyC = box(1, 1.9, .55, mat(COL.cabinet, { metal: .35, rough: .45 }));
    bodyC.position.y = .95; cab.add(bodyC);
    var door = box(.92, 1.7, .04, mat(0x415f8e, { metal: .3, rough: .4 }));
    door.position.set(0, .95, .29); cab.add(door);
    var leds = [];
    for (var i2 = 0; i2 < 3; i2++) {
      var led = box(.07, .07, .03, mat([COL.on, COL.amber, COL.accent][i2],
        { emissive: [COL.on, COL.amber, COL.accent][i2], ei: .4 }));
      led.position.set(-.28 + i2 * .28, 1.62, .32); cab.add(led); leds.push(led);
    }
    var cabLabel = labelSprite("PLC", "LS XGK");
    cabLabel.position.set(0, 2.35, 0);   // 주의: THREE 의 position 은 재할당 불가(읽기전용 프로퍼티)
    cab.add(cabLabel);
    cab.position.set(plcPos.x, 0, plcPos.z);
    scene.add(cab);
    return { leds: leds, pos: new T.Vector3(plcPos.x, 1.1, plcPos.z) };
  }

  // 배관: 경유점 곡선 튜브 + 흐름 입자 / 케이블: 바닥 라우팅 직교 튜브
  function buildPipe(scene, a, b) {
    var top = Math.max(a.y, b.y) + .9;
    var curve = new T.CatmullRomCurve3([
      new T.Vector3(a.x, a.y, a.z),
      new T.Vector3(a.x, top, a.z),
      new T.Vector3(b.x, top, b.z),
      new T.Vector3(b.x, b.y, b.z),
    ], false, "catmullrom", .08);
    var tube = new T.Mesh(new T.TubeGeometry(curve, 40, .07, 10),
      mat(COL.pipe, { metal: .6, rough: .35 }));
    tube.castShadow = true; scene.add(tube);
    var drops = [];
    for (var i = 0; i < 5; i++) {
      var dgeo = new T.Mesh(new T.SphereGeometry(.055, 8, 8),
        mat(COL.water, { emissive: COL.water, ei: .7 }));
      dgeo.visible = false; scene.add(dgeo); drops.push({ m: dgeo, t: i / 5 });
    }
    return { curve: curve, drops: drops };
  }
  function buildCable(scene, a, b) {
    var pts = [
      new T.Vector3(a.x, .06, a.z),
      new T.Vector3(a.x, .06, (a.z + b.z) / 2),
      new T.Vector3(b.x, .06, (a.z + b.z) / 2),
      new T.Vector3(b.x, .06, b.z),
    ];
    var curve = new T.CatmullRomCurve3(pts, false, "catmullrom", 0.01);
    var m = mat(COL.cable, { metal: .2, rough: .8, emissive: COL.on, ei: 0 });
    var tube = new T.Mesh(new T.TubeGeometry(curve, 24, .025, 6), m);
    scene.add(tube);
    return m;
  }

  function create(container, plant, opts) {
    var onToggle = (opts && opts.onToggle) || null;
    var W = container.clientWidth || 600, H = container.clientHeight || 360;
    var renderer = new T.WebGLRenderer({ antialias: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.setSize(W, H);
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = T.PCFSoftShadowMap;
    container.appendChild(renderer.domElement);
    var scene = new T.Scene();
    scene.background = new T.Color(0x0a0e14);
    scene.fog = new T.Fog(0x0a0e14, 20, 44);
    var cam = new T.PerspectiveCamera(45, W / H, .1, 120);

    scene.add(new T.HemisphereLight(0xa8c0dd, 0x10141a, .75));
    var sun = new T.DirectionalLight(0xfff2dd, 1.5);
    sun.position.set(7, 12, 5);
    sun.castShadow = true;
    sun.shadow.mapSize.set(1024, 1024);
    sun.shadow.camera.left = -14; sun.shadow.camera.right = 14;
    sun.shadow.camera.top = 14; sun.shadow.camera.bottom = -14;
    scene.add(sun);
    var spot = new T.SpotLight(0x9fc4ff, 12, 30, Math.PI / 5, .5);
    spot.position.set(-6, 9, -4); scene.add(spot);

    var fw = Math.max(plant.floor_w, 10), fd = Math.max(plant.floor_d, 10);
    var plcEnv = buildEnvironment(scene, fw, fd, { x: fw / 2 + 2.4, z: 1.2 });

    // 기기 세우기
    var units = [], clickables = [];
    var posOf = {};
    (plant.devices || []).forEach(function (d) {
      var build = BUILDERS[d.kind] || bActuator;
      var u = build(d);
      u.dev = d;
      u.group.position.set(d.x, 0, d.z);
      u.group.traverse(function (o) { if (o.isMesh) o.castShadow = o.castShadow !== false; });
      var sp = labelSprite(d.tag || d.symbol, d.symbol);
      sp.position.set(0, d.kind === "tank" ? 2.85 : 1.95, 0);
      u.group.add(sp);
      scene.add(u.group);
      units.push(u);
      posOf[d.symbol] = new T.Vector3(d.x, d.kind === "tank" ? 2.35 : 1.05, d.z);
      if (d.role === "input" && onToggle) {
        u.group.traverse(function (o) { if (o.isMesh) { o.userData.sym = d.symbol; clickables.push(o); } });
      }
    });

    // 실제 연결 — 배관(펌프→탱크) + 제어 케이블(기기↔PLC 캐비닛)
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

    // 카메라 궤도 + 터치(포인터) 회전·핀치 줌
    var theta = .85, phi = .95, dist = Math.max(fw, 11) * 1.15, auto = true;
    function placeCam() {
      cam.position.set(
        Math.sin(theta) * Math.cos(phi) * dist,
        Math.sin(phi) * dist * .58 + 1.4,
        Math.cos(theta) * Math.cos(phi) * dist);
      cam.lookAt(0, .9, 0);
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
      if (ids.length === 2) {                       // 핀치 줌
        pointers[e.pointerId] = { x: e.clientX, y: e.clientY };
        var a = pointers[ids[0]], b = pointers[ids[1]];
        var nd = Math.hypot(a.x - b.x, a.y - b.y);
        if (pinchD > 0) dist = Math.max(5, Math.min(40, dist * pinchD / nd));
        pinchD = nd; placeCam(); return;
      }
      var dx = e.clientX - p.x, dy = e.clientY - p.y;
      moved += Math.abs(dx) + Math.abs(dy);
      theta -= dx * .006; phi = Math.max(.22, Math.min(1.35, phi + dy * .005));
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
      dist = Math.max(5, Math.min(40, dist + e.deltaY * .012)); placeCam();
    }, { passive: false });

    var latest = null, clock = new T.Clock(), dead = false;
    function frame() {
      if (dead) return;
      requestAnimationFrame(frame);
      var dt = Math.min(clock.getDelta(), .12), t = clock.elapsedTime;
      if (auto) { theta += dt * .1; placeCam(); }
      units.forEach(function (u) { u.anim(deviceOn(u.dev, latest), t, dt); });
      // 배관 흐름 입자 + 케이블 발광 + 캐비닛 LED
      pipes.forEach(function (pp) {
        var flowing = latest && latest.outputs[pp.src];
        pp.p.drops.forEach(function (dr) {
          dr.m.visible = !!flowing;
          if (flowing) {
            dr.t = (dr.t + dt * .35) % 1;
            pp.p.curve.getPointAt(dr.t, dr.m.position);
          }
        });
      });
      for (var s in cableMats) {
        var hot = latest && (latest.outputs[s] || latest.inputs[s]);
        cableMats[s].emissiveIntensity = hot ? .8 : 0;
      }
      plcEnv.leds.forEach(function (led, i) {
        led.material.emissiveIntensity = .3 + (Math.sin(t * (2 + i)) > 0 ? .8 : 0);
      });
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
