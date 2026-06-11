/* Twin3D — WebGL 트윈 렌더러(three.js). 물리/PLC 는 twin-engine 이 소유하고
   이 모듈은 라인 상태(L.sst·PLC 출력)를 3D 메시에 바인딩만 한다.
   좌표계: 월드(x 0~17, y 0~7.7[깊이], z 높이[m]) → three(x-8.5, z, y-3.85). */
(function(){
"use strict";
const T=()=>window.THREE;
const W2T=(x,y,z)=>[x-8.5,(z||0),y-3.85];

function mat(c,o){const m=new (T()).MeshStandardMaterial(Object.assign({color:c,roughness:0.75,metalness:0.15},o||{}));return m;}
function box(w,h,d,m){const x=new (T()).Mesh(new (T()).BoxGeometry(w,h,d),m);x.castShadow=true;x.receiveShadow=true;return x;}
function cyl(r,h,m,seg){const x=new (T()).Mesh(new (T()).CylinderGeometry(r,r,h,seg||18),m);x.castShadow=true;return x;}
function at(o,x,y,z){const p=W2T(x,y,z);o.position.set(p[0],p[1],p[2]);return o;}

function hazardTex(){
  const c=document.createElement("canvas");c.width=64;c.height=16;
  const g=c.getContext("2d");g.fillStyle="#caa011";g.fillRect(0,0,64,16);
  g.fillStyle="#15161a";for(let i=-16;i<64;i+=16){g.beginPath();
    g.moveTo(i,16);g.lineTo(i+8,0);g.lineTo(i+16,0);g.lineTo(i+8,16);g.fill();}
  const t2=new (T()).CanvasTexture(c);t2.wrapS=(T()).RepeatWrapping;return t2;
}
function beltTex(len){
  const c=document.createElement("canvas");c.width=256;c.height=32;
  const g=c.getContext("2d");g.fillStyle="#11151b";g.fillRect(0,0,256,32);
  g.strokeStyle="rgba(200,215,230,.16)";g.lineWidth=2;
  for(let i=0;i<256;i+=20){g.beginPath();g.moveTo(i,0);g.lineTo(i,32);g.stroke();}
  const t2=new (T()).CanvasTexture(c);t2.wrapS=(T()).RepeatWrapping;t2.repeat.set(len/1.1,1);return t2;
}
function labelSprite(text,color){
  const c=document.createElement("canvas");c.width=256;c.height=64;
  const g=c.getContext("2d");
  g.fillStyle="rgba(13,18,25,.88)";
  g.beginPath();g.roundRect(28,8,200,44,9);g.fill();
  g.strokeStyle=color||"#3a4756";g.lineWidth=2;g.stroke();
  g.fillStyle=color||"#dce4f0";g.font="700 22px monospace";g.textAlign="center";
  g.fillText(text,128,37);
  const t2=new (T()).CanvasTexture(c);
  const sp=new (T()).Sprite(new (T()).SpriteMaterial({map:t2,transparent:true}));
  sp.scale.set(1.9,0.48,1);return sp;
}

/* ── 프리팹 ── */
function pfBelt(g,x0,y0,len,zTop){
  const dark=mat(0x39434f),steel=mat(0x274b73,{metalness:0.4,roughness:0.55});
  for(let lx=x0+0.3;lx<x0+len;lx+=1.9)for(const dy of[0.07,0.55]){
    g.add(at(box(0.09,zTop-0.13,0.09,dark),lx,y0+dy,(zTop-0.13)/2));
  }
  for(const dy of[0.035,0.585])
    g.add(at(box(len,0.13,0.07,steel),x0+len/2,y0+dy,zTop-0.065));
  const bt=beltTex(len);
  const belt=new (T()).Mesh(new (T()).BoxGeometry(len,0.02,0.46),
    new (T()).MeshStandardMaterial({map:bt,roughness:0.9}));
  at(belt,x0+len/2,y0+0.31,zTop);belt.receiveShadow=true;g.add(belt);
  for(const e of[x0,x0+len]){
    const dr=cyl(0.09,0.5,dark);dr.rotation.x=Math.PI/2;
    g.add(at(dr,e,y0+0.31,zTop-0.05));
  }
  /* drive(v,dt): 엔진 속도[m/s]를 그대로 적산 — UV = 이동거리/타일(1.1m) */
  let dist=0;
  return {tex:bt,drive:(v,dt)=>{dist+=v*dt;bt.offset.x=-dist/1.1;}};
}
function pfFence(g,x0,y0,x1,y1){
  const ym=mat(0xcaa011),ht=hazardTex();ht.repeat.set(6,1);
  const hm=new (T()).MeshBasicMaterial({map:ht});
  const seg2=(ax,ay,bx,by)=>{
    const dx=bx-ax,dy=by-ay,len=Math.hypot(dx,dy);
    const rail=new (T()).Mesh(new (T()).BoxGeometry(len,0.08,0.03),hm);
    at(rail,(ax+bx)/2,(ay+by)/2,1.36);rail.rotation.y=-Math.atan2(dy,dx);g.add(rail);
    const n=Math.max(1,Math.round(len/1.1));
    for(let i=0;i<=n;i++)g.add(at(box(0.06,1.4,0.06,ym),ax+dx*i/n,ay+dy*i/n,0.7));
  };
  seg2(x0,y0,x1,y0);seg2(x0,y0,x0,y1);seg2(x1,y0,x1,y1);
  seg2(x0,y1,x0+(x1-x0)*0.3,y1);seg2(x1-(x1-x0)*0.3,y1,x1,y1);
}
function pfAGV(){
  const g=new (T()).Group();
  const body=box(1.7,0.34,1.1,mat(0x2e5e8e,{metalness:0.3,roughness:0.5}));
  body.position.y=0.17;g.add(body);
  for(const sx of[-0.86,0.86]){
    const b2=box(0.1,0.18,1.0,mat(0xd9a514));b2.position.set(sx,0.17,0);g.add(b2);
  }
  const lidar=cyl(0.08,0.14,mat(0x1a212b));lidar.position.set(0.6,0.41,-0.18);g.add(lidar);
  const beacon=new (T()).PointLight(0x58e0ff,0,3);beacon.position.set(0.6,0.6,-0.18);g.add(beacon);
  const pal=new (T()).Group();
  const p1=box(1.2,0.12,0.85,mat(0x5a4a30));p1.position.y=0.40;pal.add(p1);
  const p2=box(1.0,0.45,0.7,mat(0x7a5c2e));p2.position.y=0.69;pal.add(p2);
  g.add(pal);
  return {group:g,beacon,pallet:pal};
}
function pfRobot(){
  const g=new (T()).Group();
  const ym=mat(0xd9a514,{roughness:0.4,metalness:0.3});
  g.add(at(cyl(0.28,0.3,mat(0xcaa011)),0,0,0.15));
  const turret=cyl(0.18,0.34,ym);turret.position.y=0.47;g.add(turret);
  const sh=new (T()).Group();sh.position.y=0.66;g.add(sh);
  const upper=box(0.16,0.85,0.16,ym);upper.position.y=0.42;sh.add(upper);
  const el=new (T()).Group();el.position.y=0.85;sh.add(el);
  const fore=box(0.13,0.8,0.13,ym);fore.position.y=0.4;el.add(fore);
  const torch=box(0.05,0.3,0.05,mat(0x39434f));torch.position.set(0,0.84,0);el.add(torch);
  const arc=new (T()).PointLight(0xbfe3ff,0,4);arc.position.set(0,1.0,0);el.add(arc);
  return {group:g,sh,el,arc};
}

function makePartsPool(env,n){
  const pool=[];
  for(let i=0;i<n;i++){
    const p=box(0.28,0.26,0.28,mat([0x3b82f6,0x7c5cff,0xd29922,0x3fa86b][i%4]));
    p.visible=false;env.set.add(p);pool.push(p);
  }
  return pool;
}

/* ── 씬 빌더(라인별) ── */
const BUILDERS={
 motor_start_stop(env){
  const bt=pfBelt(env.set,2,2.0,10,0.75);
  env.set.add(at(box(1.4,0.8,1.1,mat(0x37424f)),2.4,2.3,1.95));
  for(const[lx,ly]of[[1.8,1.85],[3.0,1.85],[1.8,2.75],[3.0,2.75]])
    env.set.add(at(box(0.14,1.55,0.14,mat(0x39434f)),lx,ly,0.78));
  env.set.add(at(box(1.0,0.5,0.95,mat(0x54442a)),12.4,2.32,0.25));
  const motor=at(box(0.4,0.26,0.3,mat(0x44528a,{metalness:0.4})),12.3,2.8,0.69);
  env.set.add(motor);
  const lamp1=new (T()).PointLight(0x3fb950,0,4);
  at(lamp1,12.85,1.65,1.4);env.set.add(lamp1);
  const lb=labelSprite("CV-101","#8ec9ff");at(lb,7,2.3,1.7);env.set.add(lb);
  const parts=[];
  for(let i=0;i<10;i++){
    const p=box(0.32,0.3,0.34,mat([0x3b82f6,0x7c5cff,0xd29922,0x3fa86b][i%4]));
    p.visible=false;env.set.add(p);parts.push(p);
  }
  env.upd=(L,dt)=>{
    bt.drive(L.sst.spd,dt); /* 엔진 램프 속도 그대로 */
    lamp1.intensity=L.plc.val("MOTOR")?1.2:0;
    parts.forEach((p,i)=>{
      const sp=L.sst.parts[i];
      if(sp){p.visible=true;const q=W2T(sp.x,2.3,sp.z+0.15);p.position.set(q[0],q[1],q[2]);}
      else p.visible=false;
    });
  };
 },
 motion_home_move(env){
  const guide=new (T()).Mesh(new (T()).BoxGeometry(10.8,0.01,0.08),
    new (T()).MeshBasicMaterial({color:0x58e0ff}));
  at(guide,8,3.0,0.012);env.set.add(guide);
  for(const[x,c,tx]of[[2.6,0x3fb950,"ST-H"],[13.4,0xd9a514,"ST-B"]]){
    const ring=new (T()).Mesh(new (T()).RingGeometry(0.7,0.78,32),
      new (T()).MeshBasicMaterial({color:c,side:2}));
    ring.rotation.x=-Math.PI/2;at(ring,x,3.0,0.015);env.set.add(ring);
    const lb=labelSprite(tx,"#9fb3c8");at(lb,x,3.0,1.5);env.set.add(lb);
  }
  env.set.add(at(box(0.3,0.85,0.9,mat(0x2f3a46)),1.85,3.0,0.43));
  const sensors=[];
  for(const sx of[3.5,6.5,9.5,12.5]){
    const s2=at(box(0.18,0.1,0.14,mat(0x1a212b)),sx,2.93,3.15);env.set.add(s2);
    const beam=new (T()).Mesh(new (T()).CylinderGeometry(0.02,0.06,2.7,8),
      new (T()).MeshBasicMaterial({color:0x58e0ff,transparent:true,opacity:0.08}));
    at(beam,sx,2.95,1.75);env.set.add(beam);
    sensors.push({x:sx,beam});
  }
  const agv=pfAGV();env.set.add(agv.group);
  const stack=[];
  for(let i=0;i<6;i++){
    const b2=box(0.55,0.42,0.55,mat(0x7a5c2e));b2.visible=false;env.set.add(b2);stack.push(b2);
  }
  const lb2=labelSprite("AGV-901","#58e0ff");env.set.add(lb2);
  env.upd=(L,dt,t)=>{
    const st=L.sst;
    const q=W2T(st.x,3.0,0);agv.group.position.set(q[0],q[1],q[2]);
    agv.pallet.visible=st.carry;
    agv.beacon.intensity=(L.plc.val("MOVING")||L.plc.val("HOMING"))&&(t*3%1)<0.6?1.6:0;
    lb2.position.set(q[0],1.6,q[2]);
    sensors.forEach(s2=>{s2.beam.material.opacity=Math.abs(st.x-s2.x)<0.45?0.4:0.08;});
    stack.forEach((b2,i)=>{
      b2.visible=i<st.stack;
      const q2=W2T(14.55+(i%3)*0.62,2.85+((i/3|0))*0.62,0.21);
      b2.position.set(q2[0],q2[1],q2[2]);
    });
  };
 },
 weld_cell(env){
  pfFence(env.set,5.0,1.2,9.7,4.5);
  const wbts=[pfBelt(env.set,1.2,2.05,3.6,0.75),
    pfBelt(env.set,9.9,2.05,3.4,0.75),
    pfBelt(env.set,5.35,2.05,1.7,0.75),
    pfBelt(env.set,8.0,2.05,1.55,0.75)];
  env.set.add(at(box(0.66,0.78,0.66,mat(0x3a4654)),7.6,2.28,0.39));
  const rob=pfRobot();
  const q0=W2T(6.3,2.95,0);rob.group.position.set(q0[0],q0[1],q0[2]);
  env.set.add(rob.group);
  const part=box(0.6,0.13,0.42,mat(0x7e8894,{metalness:0.6,roughness:0.4}));
  env.set.add(part);
  const clamps=[at(box(0.18,0.3,0.16,mat(0xb8742c)),7.27,1.96,0.93),
                at(box(0.18,0.3,0.16,mat(0xb8742c)),7.27,2.7,0.93)];
  clamps.forEach(c2=>env.set.add(c2));
  const sparks=new (T()).Points(
    new (T()).BufferGeometry().setAttribute("position",
      new (T()).BufferAttribute(new Float32Array(240*3),3)),
    new (T()).PointsMaterial({color:0xffd76b,size:0.05,transparent:true,opacity:0.95}));
  env.set.add(sparks);
  const sp=[];
  const lb=labelSprite("RB-401","#f0a14c");at(lb,6.3,2.95,2.3);env.set.add(lb);
  const SHX=6.3,SHY=2.95,SHZ=0.66,L1=0.85,L2=0.84;
  env.upd=(L,dt,t)=>{
    const st=L.sst,a0=st.arm,a=a0*a0*(3-2*a0);
    wbts.forEach(b2=>b2.drive(0.5,dt)); /* 엔진 셀 벨트 0.5m/s 동일 */
    /* 엔진과 동일한 타깃 산출(티칭 오프셋 + 위브) */
    const rc=L.devCfg["RB-401"]||{};
    const ro=rc.off||[0,0,0];
    const wv=L.plc.val("WELD")?Math.sin(st.weaveT*9)*0.07:0;
    const home=[6.85,2.95,2.0];
    const goal=[7.55+ro[0]+wv,2.3+ro[1],1.04+ro[2]];
    const tx2=home[0]+(goal[0]-home[0])*a,
          ty2=home[1]+(goal[1]-home[1])*a,
          tz2=home[2]+(goal[2]-home[2])*a;
    /* 요(턴테이블) + 평면 2링크 IK */
    const dx=tx2-SHX,dy=ty2-SHY,dz=tz2-SHZ;
    const yaw=Math.atan2(dy,dx);
    rob.group.rotation.y=-yaw;
    const r2=Math.hypot(dx,dy);
    let d=Math.hypot(r2,dz);
    d=Math.min(d,L1+L2-0.01);
    const a1=Math.atan2(dz,r2)+Math.acos((d*d+L1*L1-L2*L2)/(2*d*L1));
    const a2=Math.acos((L1*L1+L2*L2-d*d)/(2*L1*L2));
    rob.sh.rotation.z=a1-Math.PI/2;     /* 0=수직 기준 */
    rob.el.rotation.z=a2-Math.PI;       /* 펴짐=π */
    rob.arc.intensity=L.plc.val("WELD")?(2.5+Math.random()*3):0;
    const cg=st.clamp;
    const c1=W2T(7.27,1.96+cg*0.16,0.93),c2=W2T(7.27,2.7-cg*0.16,0.93);
    clamps[0].position.set(c1[0],c1[1],c1[2]);
    clamps[1].position.set(c2[0],c2[1],c2[2]);
    const px=st.out!==undefined?st.out:st.partX;
    part.visible=(st.out!==undefined||st.partX>1.55);
    const pq=W2T(px,2.34,0.84);part.position.set(pq[0],pq[1],pq[2]);
    if(L.plc.val("WELD")&&sp.length<240)
      for(let i=0;i<5;i++)sp.push({x:goal[0],y:goal[1],z:goal[2],
        vx:(Math.random()-.5)*2.4,vy:Math.random()*1.8,vz:(Math.random()-.5)*2.4,life:0.5});
    const pos=sparks.geometry.attributes.position.array;
    let n=0;
    for(let i=sp.length-1;i>=0;i--){
      const s2=sp[i];s2.life-=dt;
      if(s2.life<=0){sp.splice(i,1);continue;}
      s2.x+=s2.vx*dt;s2.z+=s2.vy*dt;s2.y+=s2.vz*dt;s2.vy-=4*dt;
      const q2=W2T(s2.x,s2.y,s2.z);
      pos[n*3]=q2[0];pos[n*3+1]=q2[1];pos[n*3+2]=q2[2];n++;
    }
    sparks.geometry.setDrawRange(0,n);
    sparks.geometry.attributes.position.needsUpdate=true;
  };
 }
,
 count_eject(env){
  const bt=pfBelt(env.set,2,2.0,11,0.75);
  for(const dy of[-0.14,0.7])
    env.set.add(at(box(0.06,1.0,0.06,mat(0x222a34)),9.19,2.0+dy+0.14,0.5));
  env.set.add(at(box(0.12,0.1,0.1,mat(0x1a212b)),9.16,2.78,0.92));
  const beam=new (T()).Mesh(new (T()).CylinderGeometry(0.015,0.015,0.86,8),
    new (T()).MeshBasicMaterial({color:0xff5b5b,transparent:true,opacity:0.25}));
  beam.rotation.x=Math.PI/2;at(beam,9.19,2.31,0.92);env.set.add(beam);
  const cylBody=at(box(0.56,0.32,0.4,mat(0x37424f)),10.7,1.62,0.78);env.set.add(cylBody);
  const rod=box(0.16,0.14,0.8,mat(0x9aa7b5,{metalness:0.6}));env.set.add(rod);
  env.set.add(at(box(0.78,0.5,0.78,mat(0x6e532a)),10.71,3.95,0.25));
  env.set.add(at(box(0.9,0.5,0.85,mat(0x54442a)),13.4,2.32,0.25));
  const lb=labelSprite("SN-101","#ff8f8f");at(lb,9.19,2.6,1.5);env.set.add(lb);
  const pool=makePartsPool(env,10);
  env.upd=(L,dt)=>{
    bt.drive(1.1*(L.speedF||1),dt); /* 검수 라인 엔진 속도식 동일 */
    beam.material.opacity=L.sst.blocked?0.95:0.22;
    const q=W2T(10.7,1.85+L.sst.rod*0.5,0.74);rod.position.set(q[0],q[1],q[2]);
    pool.forEach((p,i)=>{
      const sp=L.sst.parts[i];
      if(sp&&sp.st!==9){p.visible=true;
        const q2=W2T(sp.x,sp.y,sp.z+0.13);p.position.set(q2[0],q2[1],q2[2]);}
      else p.visible=false;
    });
  };
 },
 conveyor_divert(env){
  const bt=pfBelt(env.set,2,2.0,11,0.75);
  for(const dy of[-0.14,0.7])
    env.set.add(at(box(0.07,1.62,0.07,mat(0x39434f)),8.55,2.0+dy+0.14,0.81));
  env.set.add(at(box(0.3,0.22,0.95,mat(0x2c3743)),8.55,2.3,1.7));
  env.set.add(at(box(0.16,0.28,0.3,mat(0x1a212b)),8.55,2.33,1.42));
  const cone=new (T()).Mesh(new (T()).ConeGeometry(0.38,0.62,4),
    new (T()).MeshBasicMaterial({color:0xbfe3ff,transparent:true,opacity:0}));
  at(cone,8.55,2.33,1.05);env.set.add(cone);
  const piv=new (T()).Group();
  const q0=W2T(10.5,1.95,0.9);piv.position.set(q0[0],q0[1],q0[2]);env.set.add(piv);
  const arm=box(0.08,0.12,0.8,mat(0x566472));arm.position.z=0.4;piv.add(arm);
  env.set.add(at(box(0.85,0.5,0.8,mat(0x6e3a3a)),10.67,3.8,0.25));
  env.set.add(at(box(0.95,0.5,0.9,mat(0x3f5a3f)),13.6,2.35,0.25));
  const lb=labelSprite("VS-701","#8ec9ff");at(lb,8.55,2.3,2.15);env.set.add(lb);
  const pool=makePartsPool(env,10);
  const ngm=mat(0x8a4040);
  env.upd=(L,dt)=>{
    bt.drive(1.0*(L.speedF||1),dt); /* 비전 라인 엔진 속도식 동일 */
    cone.material.opacity=L.sst.flash*0.35;
    piv.rotation.y=-L.sst.armB*0.95;
    pool.forEach((p,i)=>{
      const sp=L.sst.parts[i];
      if(sp&&sp.st!==9){p.visible=true;
        p.material=sp.ng?ngm:p.userData.m||(p.userData.m=p.material);
        const q2=W2T(sp.x,sp.y,sp.z+0.13);p.position.set(q2[0],q2[1],q2[2]);}
      else p.visible=false;
    });
  };
 },
 cascade_conveyor(env){
  const bts=[pfBelt(env.set,1.0,2.0,5.0,1.35),
             pfBelt(env.set,6.2,2.0,5.0,0.95),
             pfBelt(env.set,11.4,2.0,5.0,0.55)];
  env.set.add(at(box(0.95,0.5,0.9,mat(0x54442a)),17.1,2.3,0.25));
  const lamps=[6.15,11.35,16.55].map((x,i)=>{
    const pl=new (T()).PointLight(0x3fb950,0,3);
    at(pl,x,2.0,[1.5,1.1,0.7][i]);env.set.add(pl);return pl;
  });
  const lb=labelSprite("CV-601~3","#7ee787");at(lb,8.6,2.3,2.2);env.set.add(lb);
  const pool=makePartsPool(env,12);
  env.upd=(L,dt)=>{
    bts.forEach((bt,i)=>bt.drive(L.sst.spd[i],dt)); /* 벨트별 램프 속도 동일 */
    const run=["CONV_UP","CONV_MID","CONV_DOWN"];
    lamps.forEach((pl,i)=>pl.intensity=L.plc.val(run[i])?1.1:0);
    pool.forEach((p,i)=>{
      const sp=L.sst.parts[i];
      if(sp&&!sp.done){p.visible=true;
        const q2=W2T(sp.x,2.32,sp.z+0.14);p.position.set(q2[0],q2[1],q2[2]);}
      else p.visible=false;
    });
  };
 },
 duty_standby(env){
  env.set.add(at(box(2.2,0.5,1.9,mat(0x2b3743)),2.45,3.0,0.25));
  const water=new (T()).Mesh(new (T()).BoxGeometry(1.9,0.06,1.6),
    new (T()).MeshStandardMaterial({color:0x2e5e8e,transparent:true,opacity:0.8}));
  at(water,2.45,3.0,0.46);env.set.add(water);
  const pumps=[];
  for(const[py,sym,tx]of[[2.35,"PUMP_LEAD","P-801A"],[3.55,"PUMP_LAG","P-801B"]]){
    env.set.add(at(box(0.6,0.5,0.6,mat(0x44528a)),4.75,py,0.25));
    const vol=cyl(0.26,0.45,mat(0x3a4654));at(vol,5.3,py,0.22);env.set.add(vol);
    const pl=new (T()).PointLight(0x3fb950,0,2.5);at(pl,5.3,py,0.7);env.set.add(pl);
    const lb2=labelSprite(tx,"#8ec9ff");at(lb2,4.95,py,1.25);env.set.add(lb2);
    const pipe=new (T()).Mesh(new (T()).CylinderGeometry(0.05,0.05,5.4,10),
      new (T()).MeshStandardMaterial({color:0x566472,metalness:0.5,roughness:0.5,emissive:0x000000}));
    pipe.rotation.z=Math.PI/2;at(pipe,8.3,py,2.7);env.set.add(pipe);
    const rise=new (T()).Mesh(new (T()).CylinderGeometry(0.05,0.05,2.45,10),pipe.material);
    at(rise,5.6,py,1.5);env.set.add(rise);
    pumps.push({sym,pl,pm:pipe.material});
  }
  const tank=cyl(1.05,2.3,mat(0x46535f,{roughness:0.5}));at(tank,11.5,3.0,1.7);env.set.add(tank);
  for(const[lx,ly]of[[10.6,2.3],[12.4,2.3],[10.6,3.7],[12.4,3.7]])
    env.set.add(at(box(0.16,0.55,0.16,mat(0x39434f)),lx,ly,0.28));
  const gauge=new (T()).Mesh(new (T()).BoxGeometry(0.08,1.94,0.04),
    new (T()).MeshBasicMaterial({color:0x58a6ff}));
  env.set.add(gauge);
  const lb3=labelSprite("TK-801","#9fb3c8");at(lb3,11.5,3.0,3.3);env.set.add(lb3);
  env.upd=(L,dt,t)=>{
    const st=L.sst;
    pumps.forEach(p2=>{
      const on=L.plc.val(p2.sym);
      p2.pl.intensity=on?1.2:0;
      p2.pm.emissive.setHex(on?0x1a4a6e:0x000000);
    });
    const h=Math.max(0.02,st.level*1.94);
    gauge.scale.y=h/1.94;
    const q=W2T(12.65,3.55,0.62+h/2);gauge.position.set(q[0],q[1],q[2]);
  };
 }
,
 fwd_rev(env){
  for(const dy of[0.0,0.6])
    env.set.add(at(box(11.4,0.09,0.07,mat(0x566472,{metalness:0.5})),7.6,2.9+dy+0.05,0.14));
  for(let x=2;x<=12.8;x+=0.85)
    env.set.add(at(box(0.5,0.05,0.74,mat(0x2a323c)),x+0.25,3.25,0.025));
  env.set.add(at(box(1.3,0.55,1.4,mat(0x37424f)),1.2,3.3,0.28));
  env.set.add(at(box(1.4,0.55,1.4,mat(0x37424f)),14.15,3.3,0.28));
  for(const[wx,tx]of[[1.1,"M-202"],[13.7,"M-201"]]){
    env.set.add(at(box(0.45,0.5,0.45,mat(0x44528a)),wx,3.97,0.25));
    const lb2=labelSprite(tx,"#8ec9ff");at(lb2,wx,3.97,1.1);env.set.add(lb2);
  }
  const car=new (T()).Group();env.set.add(car);
  const body=box(1.5,0.42,1.0,mat(0x3a4656));body.position.y=0.35;car.add(body);
  const crate=box(0.85,0.6,0.8,mat(0x7a5c2e));crate.position.y=0.86;car.add(crate);
  const bk=new (T()).PointLight(0x58a6ff,0,3);bk.position.y=1.1;car.add(bk);
  const lb=labelSprite("SH-201","#dce4f0");env.set.add(lb);
  const stack=[];
  for(let i=0;i<7;i++){
    const b2=box(0.55,0.42,0.55,mat(0x7a5c2e));b2.visible=false;env.set.add(b2);stack.push(b2);
  }
  env.upd=(L,dt,t)=>{
    const st=L.sst;
    const q=W2T(st.pos,3.25,0);car.position.set(q[0],q[1],q[2]);
    crate.visible=st.carry||st.anim>0;
    const f=L.plc.val("MOTOR_FWD"),r2=L.plc.val("MOTOR_REV");
    bk.color.setHex(f?0x58a6ff:0x9b7bff);
    bk.intensity=(f||r2)?1.4:0;
    lb.position.set(q[0],1.7,q[2]);
    stack.forEach((b2,i)=>{
      b2.visible=i<st.stackN;
      const q2=W2T(13.7+(i%2)*0.62,2.85+((i/2|0)%2)*0.62,0.76+(i/4|0)*0.45);
      b2.position.set(q2[0],q2[1],q2[2]);
    });
  };
 },
 car_wash(env){
  env.set.add(at(box(17.2,0.06,2.1,mat(0x1a212a)),8.9,2.95,0.03));
  const arches=[];
  for(const[x,c,tx]of[[5,0x58a6ff,"V-301"],[8,0x7c5cff,"P-301"],[11,0xd9a514,"FN-301"]]){
    const am=mat(0x2c3743);
    for(const ay of[1.75,3.75])env.set.add(at(box(0.28,2.45,0.28,am),x,ay,1.225));
    const beam=box(0.4,0.3,2.28,new (T()).MeshStandardMaterial({color:0x2c3743,emissive:0x000000}));
    at(beam,x,2.75,2.6);env.set.add(beam);
    const lb2=labelSprite(tx,"#9fb3c8");at(lb2,x,2.0,3.2);env.set.add(lb2);
    arches.push({c,beam});
  }
  const car=new (T()).Group();env.set.add(car);
  const body=box(4.3,0.6,1.7,mat(0xa83248,{metalness:0.5,roughness:0.4}));
  body.position.y=0.62;car.add(body);
  const cabin=box(2.05,0.55,1.5,mat(0x1d2a3a,{metalness:0.7,roughness:0.25}));
  cabin.position.set(0.1,1.2,0);car.add(cabin);
  for(const[wx,wz]of[[-1.3,-0.85],[1.3,-0.85],[-1.3,0.85],[1.3,0.85]]){
    const wh=cyl(0.32,0.24,mat(0x11161d));wh.rotation.x=Math.PI/2;
    wh.position.set(wx,0.32,wz);car.add(wh);
  }
  env.upd=(L,dt)=>{
    const st=L.sst;
    const q=W2T(st.carX,2.95,0);car.position.set(q[0],q[1],q[2]);
    car.visible=st.carX>-3.5&&st.carX<19.5;
    const on=[L.plc.val("SOAP"),L.plc.val("RINSE"),L.plc.val("DRY")];
    arches.forEach((a2,i)=>a2.beam.material.emissive.setHex(on[i]?a2.c:0x000000));
  };
 },
 batch_fill_mix_drain(env){
  for(const[lx,ly]of[[5.2,2.0],[6.9,2.0],[5.2,3.3],[6.9,3.3]])
    env.set.add(at(box(0.14,0.55,0.14,mat(0x39434f)),lx,ly,0.28));
  const tank=cyl(1.05,2.1,mat(0x46535f,{roughness:0.45,metalness:0.3}));
  at(tank,6.05,2.66,1.6);env.set.add(tank);
  const liquid=new (T()).Mesh(new (T()).CylinderGeometry(0.98,0.98,1,24),
    new (T()).MeshStandardMaterial({color:0x2e7ec8,transparent:true,opacity:0.55}));
  env.set.add(liquid);
  env.set.add(at(box(0.5,0.42,0.45,mat(0x44528a)),6.0,2.6,2.86));
  const shaft=cyl(0.04,1.8,mat(0x9aa7b5,{metalness:0.7}));
  at(shaft,6.05,2.66,1.7);env.set.add(shaft);
  const fillPipe=new (T()).Mesh(new (T()).CylinderGeometry(0.05,0.05,4.6,10),
    new (T()).MeshStandardMaterial({color:0x566472,emissive:0x000000,metalness:0.5}));
  fillPipe.rotation.z=Math.PI/2;at(fillPipe,3.7,2.6,3.3);env.set.add(fillPipe);
  const drainPipe=new (T()).Mesh(new (T()).CylinderGeometry(0.05,0.05,1.9,10),
    new (T()).MeshStandardMaterial({color:0x566472,emissive:0x000000,metalness:0.5}));
  drainPipe.rotation.z=Math.PI/2;at(drainPipe,7.9,3.32,0.5);env.set.add(drainPipe);
  const drum=cyl(0.4,0.92,mat(0x2e5e8e));env.set.add(drum);
  const lb=labelSprite("TK-501","#9fb3c8");at(lb,6.05,2.66,3.4);env.set.add(lb);
  env.upd=(L,dt,t)=>{
    const st=L.sst;
    const h=Math.max(0.02,st.level*1.9);
    liquid.scale.y=h;
    const q=W2T(6.05,2.66,0.6+h/2);liquid.position.set(q[0],q[1],q[2]);
    if(L.plc.val("MIXER"))shaft.rotation.y+=dt*9;
    fillPipe.material.emissive.setHex(L.plc.val("FILL_VALVE")?0x1a4a6e:0x000000);
    drainPipe.material.emissive.setHex(L.plc.val("DRAIN_VALVE")?0x1a5e34:0x000000);
    const q2=W2T(st.drumX,3.45,0.46);drum.position.set(q2[0],q2[1],q2[2]);
    drum.scale.y=0.3+0.7*Math.max(0.05,st.drum);
  };
 }
};

const Twin3D={
 supported:Object.keys(BUILDERS),
 active:null,
 _r:null,_scene:null,_cam:null,_env:null,_orbit:{th:0.95,ph:0.42,d:12},
 mount(container,L){
  const TT=T();
  this.destroy();
  const W=container.clientWidth,H=container.clientHeight;
  const r=new TT.WebGLRenderer({antialias:true});
  r.setSize(W,H);r.setPixelRatio(Math.min(devicePixelRatio,2));
  r.shadowMap.enabled=true;
  if(TT.PCFSoftShadowMap!==undefined)r.shadowMap.type=TT.PCFSoftShadowMap;
  if(TT.ACESFilmicToneMapping!==undefined){r.toneMapping=TT.ACESFilmicToneMapping;r.toneMappingExposure=1.05;}
  if(TT.SRGBColorSpace!==undefined)r.outputColorSpace=TT.SRGBColorSpace;
  else if(TT.sRGBEncoding!==undefined)r.outputEncoding=TT.sRGBEncoding;
  container.appendChild(r.domElement);
  const sc=new TT.Scene();
  sc.background=new TT.Color(0x0a0f16);
  sc.fog=new TT.Fog(0x0a0f16,20,55);
  sc.add(new TT.AmbientLight(0x7788aa,0.35));
  sc.add(new TT.HemisphereLight(0x9db4d8,0x1a1f27,0.5));
  const sun=new TT.DirectionalLight(0xffeedd,1.0);
  sun.position.set(7,13,5);sun.castShadow=true;
  sun.shadow.mapSize.set(2048,2048);
  sun.shadow.camera.left=-12;sun.shadow.camera.right=12;
  sun.shadow.camera.top=12;sun.shadow.camera.bottom=-12;
  sc.add(sun);
  const fc=document.createElement("canvas");fc.width=512;fc.height=512;
  const fg=fc.getContext("2d");
  fg.fillStyle="#262c34";fg.fillRect(0,0,512,512);
  for(let i=0;i<2600;i++){fg.fillStyle="rgba("+(20+Math.random()*40|0)+","+(24+Math.random()*44|0)+","+(30+Math.random()*48|0)+",.35)";
    fg.fillRect(Math.random()*512,Math.random()*512,2,2);}
  fg.strokeStyle="rgba(0,0,0,.45)";fg.lineWidth=3;
  for(let i=0;i<=512;i+=128){fg.beginPath();fg.moveTo(i,0);fg.lineTo(i,512);fg.stroke();
    fg.beginPath();fg.moveTo(0,i);fg.lineTo(512,i);fg.stroke();}
  const ftex=new TT.CanvasTexture(fc);
  ftex.wrapS=ftex.wrapT=TT.RepeatWrapping;ftex.repeat.set(6,4);
  const floor=new TT.Mesh(new TT.PlaneGeometry(26,16),
    new TT.MeshStandardMaterial({map:ftex,roughness:0.92}));
  floor.rotation.x=-Math.PI/2;floor.receiveShadow=true;sc.add(floor);
  const grid=new TT.GridHelper(26,26,0x33404e,0x191f27);
  grid.position.y=0.002;sc.add(grid);
  const cam=new TT.PerspectiveCamera(50,W/H,0.1,120);
  const env={set:new TT.Group(),upd:null};
  sc.add(env.set);
  BUILDERS[L.id](env);
  this._r=r;this._scene=sc;this._cam=cam;this._env=env;this.active=L.id;
  this._bindOrbit(container);
  this._camUpd();
 },
 _bindOrbit(el){
  let drag=null;
  el.onpointerdown=e=>{drag={x:e.clientX,y:e.clientY};};
  el.onpointermove=e=>{if(!drag)return;
    this._orbit.th+=(e.clientX-drag.x)*0.005;
    this._orbit.ph=Math.min(1.4,Math.max(0.08,this._orbit.ph+(e.clientY-drag.y)*0.004));
    drag={x:e.clientX,y:e.clientY};};
  el.onpointerup=()=>{drag=null;};
  el.onwheel=e=>{e.preventDefault();
    this._orbit.d=Math.min(34,Math.max(3.5,this._orbit.d*Math.exp(e.deltaY*0.001)));};
 },
 _camUpd(){
  const o=this._orbit;
  this._cam.position.set(o.d*Math.cos(o.ph)*Math.cos(o.th),
    0.7+o.d*Math.sin(o.ph),o.d*Math.cos(o.ph)*Math.sin(o.th));
  this._cam.lookAt(0,0.6,0);
 },
 update(L,dt,t){
  if(!this._r||this.active!==L.id)return;
  if(this._env.upd)this._env.upd(L,dt,t);
  this._camUpd();
  this._r.render(this._scene,this._cam);
 },
 resize(container){
  if(!this._r)return;
  const W=container.clientWidth,H=container.clientHeight;
  this._r.setSize(W,H);this._cam.aspect=W/H;this._cam.updateProjectionMatrix();
 },
 destroy(){
  if(this._r){this._r.dispose();
    if(this._r.domElement.parentNode)this._r.domElement.parentNode.removeChild(this._r.domElement);}
  this._r=null;this._scene=null;this._env=null;this.active=null;
 }
};
window.Twin3D=Twin3D;
})();
