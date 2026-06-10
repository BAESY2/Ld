/* plant3d.js — 3D 가상 공장 렌더러 (Three.js, 서버 PlantLayout 기반).
 *
 * 서버 /api/compile 의 plant(설비 배치도: 기기 종류·좌표·탱크·계기)를 받아
 * 3D 공장을 세우고, 검증된 ST 스캔 루프(SimEngine)의 매 스캔 상태로 기기를
 * 실가동한다(모터 회전·펌프 맥동·밸브 개폐·히터 발광·경광등 점멸·탱크 수위·
 * 컨베이어 이송·실린더 왕복). 조작반 버튼은 3D 에서 직접 클릭해 입력 토글.
 *
 * window.Plant3D.create(container, plant, {onToggle}) ->
 *   { update(simResult), resize(), destroy() }
 * simResult = SimEngine.step() 반환 {inputs, outputs, table}.
 */
(function () {
  "use strict";
  if (!window.THREE) { window.Plant3D = null; return; }
  var T = window.THREE;

  var COL = {
    floor: 0x10151c, grid: 0x223040, steel: 0x8a97a8, dark: 0x39424f,
    on: 0x3fb950, off: 0x2c3540, accent: 0x58a6ff, red: 0xff4d4d,
    amber: 0xd29922, water: 0x2f81f7, glass: 0x9fb9d8,
  };

  function mat(color, opts) {
    var o = opts || {};
    return new T.MeshStandardMaterial({
      color: color, roughness: o.rough != null ? o.rough : .55,
      metalness: o.metal != null ? o.metal : .35,
      transparent: !!o.alpha, opacity: o.alpha || 1,
      emissive: o.emissive || 0x000000, emissiveIntensity: o.ei || 1,
    });
  }
  function box(w, h, d, m) { return new T.Mesh(new T.BoxGeometry(w, h, d), m); }
  function cyl(rt, rb, h, m, seg) {
    return new T.Mesh(new T.CylinderGeometry(rt, rb, h, seg || 24), m);
  }

  // 라벨 스프라이트(캔버스 텍스트) — 심볼/한국어 라벨을 기기 위에 띄운다.
  function labelSprite(text) {
    var c = document.createElement("canvas");
    var ctx = c.getContext("2d");
    ctx.font = "600 26px system-ui, sans-serif";
    var w = Math.ceil(ctx.measureText(text).width) + 26;
    c.width = w; c.height = 44;
    ctx = c.getContext("2d");
    ctx.font = "600 26px system-ui, sans-serif";
    ctx.fillStyle = "rgba(10,16,24,.78)";
    ctx.beginPath();
    if (ctx.roundRect) ctx.roundRect(0, 0, w, 44, 10); else ctx.rect(0, 0, w, 44);
    ctx.fill();
    ctx.fillStyle = "#cfe3ff"; ctx.textBaseline = "middle";
    ctx.fillText(text, 13, 23);
    var tex = new T.CanvasTexture(c);
    var sp = new T.Sprite(new T.SpriteMaterial({ map: tex, depthTest: false }));
    sp.scale.set(w / 110, .4, 1);
    return sp;
  }

  // ── 기기 빌더 — 각 빌더는 {group, anim(state, t, dt)} 반환 ──────────────────
  function bMotor(d) {
    var g = new T.Group();
    g.add(Object.assign(box(1.1, .22, .8, mat(COL.dark)), { position: new T.Vector3(0, .11, 0) }));
    var body = cyl(.34, .34, .8, mat(COL.steel, { metal: .6 }));
    body.rotation.z = Math.PI / 2; body.position.y = .55; g.add(body);
    var ring = cyl(.36, .36, .12, mat(COL.off, { emissive: COL.on, ei: 0 }));
    ring.rotation.z = Math.PI / 2; ring.position.set(-.36, .55, 0); g.add(ring);
    var rotor = new T.Group(); rotor.position.set(.52, .55, 0);
    for (var i = 0; i < 3; i++) {
      var bl = box(.05, .42, .1, mat(COL.accent, { metal: .2 }));
      bl.position.y = .2; var hold = new T.Group();
      hold.rotation.x = i * Math.PI * 2 / 3; hold.add(bl); rotor.add(hold);
    }
    rotor.rotation.z = Math.PI / 2; g.add(rotor);
    return { group: g, anim: function (on, t, dt) {
      if (on) rotor.rotateOnAxis(new T.Vector3(0, 1, 0), dt * 9);
      ring.material.emissiveIntensity = on ? 1.4 : 0;
    } };
  }
  function bPump(d) {
    var g = new T.Group();
    g.add(Object.assign(box(.9, .2, .9, mat(COL.dark)), { position: new T.Vector3(0, .1, 0) }));
    var body = cyl(.38, .44, .62, mat(COL.steel, { metal: .55 }));
    body.position.y = .5; g.add(body);
    var dome = new T.Mesh(new T.SphereGeometry(.38, 24, 16, 0, Math.PI * 2, 0, Math.PI / 2),
      mat(COL.accent, { emissive: COL.accent, ei: 0 }));
    dome.position.y = .81; g.add(dome);
    return { group: g, anim: function (on, t) {
      var s = on ? 1 + Math.sin(t * 14) * .045 : 1;
      dome.scale.set(s, s, s);
      dome.material.emissiveIntensity = on ? .9 : 0;
    } };
  }
  function bValve(d) {
    var g = new T.Group();
    var pipe = cyl(.16, .16, 1.5, mat(COL.steel, { metal: .65 }));
    pipe.rotation.z = Math.PI / 2; pipe.position.y = .45; g.add(pipe);
    var bodyV = cyl(.24, .24, .4, mat(COL.dark)); bodyV.position.y = .55; g.add(bodyV);
    var wheel = new T.Mesh(new T.TorusGeometry(.26, .05, 10, 24),
      mat(COL.red, { emissive: COL.on, ei: 0 }));
    wheel.rotation.x = Math.PI / 2; wheel.position.y = .92; g.add(wheel);
    return { group: g, anim: function (on, t, dt) {
      if (on && wheel.rotation.z < Math.PI / 2) wheel.rotation.z += dt * 3;
      if (!on && wheel.rotation.z > 0) wheel.rotation.z -= dt * 3;
      wheel.material.color.set(on ? COL.on : COL.red);
      wheel.material.emissiveIntensity = on ? .8 : 0;
    } };
  }
  function bHeater(d) {
    var g = new T.Group();
    var body = box(.95, .9, .8, mat(0x4a3325, { rough: .7 })); body.position.y = .45; g.add(body);
    var coil = box(.8, .55, .06, mat(0xff5a1f, { emissive: 0xff5a1f, ei: 0 }));
    coil.position.set(0, .5, .41); g.add(coil);
    return { group: g, anim: function (on, t) {
      coil.material.emissiveIntensity = on ? 1.6 + Math.sin(t * 6) * .35 : 0;
    } };
  }
  function bFan(d) {
    var g = new T.Group();
    var pole = cyl(.07, .09, 1, mat(COL.steel)); pole.position.y = .5; g.add(pole);
    var hub = new T.Group(); hub.position.y = 1.08;
    for (var i = 0; i < 4; i++) {
      var bl = box(.07, .5, .14, mat(0x7fd2ff, { metal: .1 }));
      bl.position.y = .26; var hold = new T.Group();
      hold.rotation.z = i * Math.PI / 2; hold.add(bl); hub.add(hold);
    }
    g.add(hub);
    return { group: g, anim: function (on, t, dt) {
      if (on) hub.rotateOnAxis(new T.Vector3(0, 0, 1), dt * 10);
    } };
  }
  function bConveyor(d) {
    var g = new T.Group();
    var bed = box(2.1, .16, .8, mat(COL.dark)); bed.position.y = .5; g.add(bed);
    [-0.9, 0.9].forEach(function (x) {
      var leg = box(.1, .5, .7, mat(COL.steel)); leg.position.set(x, .25, 0); g.add(leg);
    });
    var items = [];
    for (var i = 0; i < 3; i++) {
      var it = box(.26, .26, .26, mat(COL.amber, { rough: .8, metal: .05 }));
      it.position.set(-1 + i * .7, .71, 0); g.add(it); items.push(it);
    }
    return { group: g, anim: function (on, t, dt) {
      if (!on) return;
      items.forEach(function (it) {
        it.position.x += dt * .9;
        if (it.position.x > 1.05) it.position.x = -1.05;
      });
    } };
  }
  function bBeacon(d) {
    var g = new T.Group();
    var pole = cyl(.06, .08, .9, mat(COL.steel)); pole.position.y = .45; g.add(pole);
    var lamp = new T.Mesh(new T.SphereGeometry(.2, 18, 14),
      mat(COL.red, { emissive: COL.red, ei: 0, alpha: .95 }));
    lamp.position.y = 1.05; g.add(lamp);
    var light = new T.PointLight(COL.red, 0, 5); light.position.y = 1.05; g.add(light);
    return { group: g, anim: function (on, t) {
      var f = on ? (Math.sin(t * 10) > 0 ? 1.8 : .15) : 0;
      lamp.material.emissiveIntensity = f; light.intensity = f * 1.2;
    } };
  }
  function bEjector(d) {
    var g = new T.Group();
    var base = box(.5, .5, .5, mat(COL.dark)); base.position.y = .25; g.add(base);
    var rod = cyl(.07, .07, .7, mat(COL.steel, { metal: .7 }));
    rod.rotation.x = Math.PI / 2; rod.position.set(0, .35, .35); g.add(rod);
    var head = box(.4, .4, .12, mat(COL.amber)); head.position.set(0, .35, .75); g.add(head);
    return { group: g, anim: function (on, t, dt) {
      var target = on ? 1.15 : .75;
      head.position.z += (target - head.position.z) * Math.min(1, dt * 8);
      rod.scale.y = (head.position.z - .35) / .4;
      rod.position.z = (.35 + head.position.z) / 2 - .175;
    } };
  }
  function bGate(d) {
    var g = new T.Group();
    [-0.55, 0.55].forEach(function (x) {
      var post = box(.12, 1.3, .12, mat(COL.steel)); post.position.set(x, .65, 0); g.add(post);
    });
    var panel = box(1, .9, .07, mat(COL.accent, { alpha: .85 })); panel.position.y = .5; g.add(panel);
    return { group: g, anim: function (on, t, dt) {
      var target = on ? 1.15 : .5;
      panel.position.y += (target - panel.position.y) * Math.min(1, dt * 6);
    } };
  }
  function bMixer(d) {
    var g = new T.Group();
    var vessel = cyl(.45, .35, .8, mat(COL.glass, { alpha: .35, rough: .15 }));
    vessel.position.y = .45; g.add(vessel);
    var shaft = new T.Group(); shaft.position.y = .55;
    var blade = box(.6, .08, .12, mat(COL.steel, { metal: .7 })); shaft.add(blade);
    g.add(shaft);
    return { group: g, anim: function (on, t, dt) {
      if (on) shaft.rotateOnAxis(new T.Vector3(0, 1, 0), dt * 7);
    } };
  }
  function bActuator(d) {
    var g = new T.Group();
    var body = box(.7, .7, .7, mat(COL.dark, { emissive: COL.on, ei: 0 }));
    body.position.y = .35; g.add(body);
    return { group: g, anim: function (on) {
      body.material.emissiveIntensity = on ? .8 : 0;
    } };
  }
  function bTank(d) {
    var g = new T.Group();
    var shell = cyl(.62, .62, 1.5, mat(COL.glass, { alpha: .22, rough: .1, metal: .1 }));
    shell.position.y = .8; g.add(shell);
    var water = cyl(.56, .56, 1, mat(COL.water, { alpha: .75, rough: .2, metal: 0 }));
    water.position.y = .55; water.scale.y = .35; g.add(water);
    [.35, 1.25].forEach(function (y) {
      var markL = new T.Mesh(new T.TorusGeometry(.63, .015, 6, 32), mat(COL.amber));
      markL.rotation.x = Math.PI / 2; markL.position.y = y; g.add(markL);
    });
    var level = .35;
    return { group: g, anim: function (on, t, dt) {
      // on = 채우는 기기(펌프/밸브) 중 하나라도 가동 — 차오르고, 아니면 천천히 빠진다.
      level += (on ? .11 : -.05) * dt;
      level = Math.max(.06, Math.min(.95, level));
      water.scale.y = level;
      water.position.y = .08 + level * 1.4 / 2 + .05;
    } };
  }
  function bGauge(d) {
    var g = new T.Group();
    var pole = box(.12, 1.1, .12, mat(COL.steel)); pole.position.y = .55; g.add(pole);
    var panel = box(.6, .9, .08, mat(0x0d1420, { rough: .4 })); panel.position.y = 1.2; g.add(panel);
    var bar = box(.16, .8, .04, mat(COL.on, { emissive: COL.on, ei: .5 }));
    bar.position.set(-.12, 1.2, .07); bar.scale.y = .12; g.add(bar);
    var mark = box(.3, .03, .05, mat(COL.amber, { emissive: COL.amber, ei: .8 }));
    mark.position.set(.1, 1.2, .07); g.add(mark);
    var lvl = .12;
    return { group: g, anim: function (on, t, dt) {
      // on = 이 신호의 임계 플래그 중 하나가 참 — 바가 임계선 위로 차오른다.
      var target = on ? .85 : .12;
      lvl += (target - lvl) * Math.min(1, dt * 2.2);
      bar.scale.y = lvl;
      bar.position.y = 1.2 - .4 + lvl * .4;
      bar.material.color.set(on ? COL.red : COL.on);
      bar.material.emissive.set(on ? COL.red : COL.on);
    } };
  }
  function bInput(d) {
    var g = new T.Group();
    var ped = cyl(.16, .2, .55, mat(COL.dark)); ped.position.y = .27; g.add(ped);
    var capCol = d.kind === "estop" ? COL.red
      : d.kind === "button" ? COL.on
      : d.kind === "fault" ? COL.amber : COL.accent;
    var capGeo = d.kind === "estop"
      ? new T.CylinderGeometry(.17, .17, .12, 20)
      : new T.SphereGeometry(.14, 16, 12);
    var cap = new T.Mesh(capGeo, mat(capCol, { emissive: capCol, ei: 0 }));
    cap.position.y = .62; g.add(cap);
    return { group: g, anim: function (on, t) {
      cap.material.emissiveIntensity = on ? 1.5 : 0;
      cap.position.y = on ? .58 : .62;
    } };
  }

  var BUILDERS = {
    motor: bMotor, pump: bPump, valve: bValve, heater: bHeater, cooler: bFan,
    fan: bFan, conveyor: bConveyor, beacon: bBeacon, ejector: bEjector,
    gate: bGate, mixer: bMixer, actuator: bActuator, tank: bTank, gauge: bGauge,
    button: bInput, estop: bInput, level: bInput, fault: bInput, sensor: bInput,
  };

  // 기기 on 여부 — role 별로 시뮬 상태에서 읽는다.
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
      // 신호명_GE/LE 임계 플래그(시뮬에선 입력 스위치) 중 참이 있으면 '임계 도달'.
      for (var k in r.inputs)
        if (k.indexOf(d.symbol + "_") === 0 && r.inputs[k]) return true;
      return false;
    }
    return false;
  }

  function create(container, plant, opts) {
    var onToggle = (opts && opts.onToggle) || null;
    var W = container.clientWidth || 600, H = container.clientHeight || 360;
    var renderer = new T.WebGLRenderer({ antialias: true, alpha: false });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.setSize(W, H);
    container.appendChild(renderer.domElement);
    var scene = new T.Scene();
    scene.background = new T.Color(0x070b11);
    scene.fog = new T.Fog(0x070b11, 16, 34);
    var cam = new T.PerspectiveCamera(46, W / H, .1, 100);

    scene.add(new T.HemisphereLight(0x9db8d8, 0x141a22, .9));
    var sun = new T.DirectionalLight(0xffffff, 1.1);
    sun.position.set(6, 10, 4); scene.add(sun);

    var fw = Math.max(plant.floor_w, 10), fd = Math.max(plant.floor_d, 10);
    var floor = new T.Mesh(new T.PlaneGeometry(fw + 6, fd + 6),
      mat(COL.floor, { rough: .9, metal: .05 }));
    floor.rotation.x = -Math.PI / 2; scene.add(floor);
    scene.add(new T.GridHelper(Math.max(fw, fd) + 6, Math.max(fw, fd) + 6,
      COL.grid, COL.grid));

    // 기기 세우기
    var units = [];
    var clickables = [];
    (plant.devices || []).forEach(function (d) {
      var build = BUILDERS[d.kind] || bActuator;
      var u = build(d);
      u.dev = d;
      u.group.position.set(d.x, 0, d.z);
      var sp = labelSprite(d.symbol);
      sp.position.set(0, d.kind === "tank" ? 1.95 : 1.55, 0);
      u.group.add(sp);
      scene.add(u.group);
      units.push(u);
      if (d.role === "input" && onToggle) {
        u.group.traverse(function (o) { if (o.isMesh) { o.userData.sym = d.symbol; clickables.push(o); } });
      }
    });

    // 카메라 궤도(드래그 회전·휠 줌·자동 선회)
    var theta = .9, phi = 1.05, dist = Math.max(fw, 11) * 1.05, auto = true;
    function placeCam() {
      cam.position.set(
        Math.sin(theta) * Math.cos(phi) * dist,
        Math.sin(phi) * dist * .62 + 1.2,
        Math.cos(theta) * Math.cos(phi) * dist);
      cam.lookAt(0, .6, 0);
    }
    placeCam();
    var dragging = false, px = 0, py = 0, moved = 0;
    var el = renderer.domElement;
    el.style.touchAction = "none";
    el.addEventListener("pointerdown", function (e) {
      dragging = true; auto = false; moved = 0; px = e.clientX; py = e.clientY;
      el.setPointerCapture(e.pointerId);
    });
    el.addEventListener("pointermove", function (e) {
      if (!dragging) return;
      var dx = e.clientX - px, dy = e.clientY - py;
      moved += Math.abs(dx) + Math.abs(dy);
      theta -= dx * .006; phi = Math.max(.25, Math.min(1.35, phi + dy * .005));
      px = e.clientX; py = e.clientY; placeCam();
    });
    el.addEventListener("pointerup", function (e) {
      dragging = false;
      if (moved < 6 && onToggle && clickables.length) {  // 클릭 = 조작반 버튼 토글
        var rect = el.getBoundingClientRect();
        var v = new T.Vector2(
          ((e.clientX - rect.left) / rect.width) * 2 - 1,
          -((e.clientY - rect.top) / rect.height) * 2 + 1);
        var rc = new T.Raycaster(); rc.setFromCamera(v, cam);
        var hit = rc.intersectObjects(clickables, false)[0];
        if (hit && hit.object.userData.sym) onToggle(hit.object.userData.sym);
      }
    });
    el.addEventListener("wheel", function (e) {
      e.preventDefault();
      dist = Math.max(5, Math.min(34, dist + e.deltaY * .012)); placeCam();
    }, { passive: false });

    // 렌더 루프 — 최신 스캔 상태(latest)로 60fps 보간 애니메이션
    var latest = null, clock = new T.Clock(), dead = false;
    function frame() {
      if (dead) return;
      requestAnimationFrame(frame);
      var dt = Math.min(clock.getDelta(), .12), t = clock.elapsedTime;
      if (auto) { theta += dt * .12; placeCam(); }
      units.forEach(function (u) { u.anim(deviceOn(u.dev, latest), t, dt); });
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
