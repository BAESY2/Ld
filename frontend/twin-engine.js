/* Hands 트윈 엔진 — 가상 PLC·씬·KPI·코사임 (빌드 시 docs/demo 에 인라인됨)
   소스 오브 트루스: 이 파일 + investor-demo.html. docs/demo/index.html 은
   scripts/build_demo.py 산출물 — 직접 수정 금지. */
const DEMO = {"motor_start_stop": {"title": "모터 기동/정지(자기유지)","st": "MOTOR := ((START AND NOT STOP) OR MOTOR) AND NOT ((STOP));","ladder": {"title": "모터 기동/정지(자기유지)","rungs": [{"comment": "","input_branches": [{"elements": [{"element_type": "CONTACT_NO","symbol": "START","address": "","description": ""},{"element_type": "CONTACT_NC","symbol": "STOP","address": "","description": ""}]},{"elements": [{"element_type": "CONTACT_NO","symbol": "MOTOR","address": "","description": ""},{"element_type": "CONTACT_NC","symbol": "STOP","address": "","description": ""}]}],"outputs": [{"element_type": "COIL","symbol": "MOTOR","address": "","description": ""}]}]},"explain": "## 이 장치는 무엇을 하나요\n■ 모터 기동/정지(자기유지)\n입력(사람·센서 신호): START(기동 버튼), STOP(정지 버튼)\n출력(움직이는 것): MOTOR(모터)\n\n## 동작 설명 (한 줄씩)\n- 렁 1: (START가 켜져 있음, STOP가 꺼져 있음) 또는 (MOTOR가 켜져 있음, STOP가 꺼져 있음) 면 MOTOR가 켜집니다. (자기유지: 한 번 켜지면 정지 조건 전까지 유지)\n\n## 안전·검증\n- ✅ 로직 검사 통과 — 이중 코일·인터록 로직·도달성에 문제가 없습니다.\n- ℹ️ 이는 로직 검사이며 기능 안전 인증이 아닙니다. E-stop·가드 등 안전기능은 하드와이어로 구현하세요.","passed": true,"sim": {"inputs": ["START","STOP"],"outputs": ["MOTOR"],"samples": [{"t": 0,"i": {"START": true,"STOP": false},"o": {"MOTOR": true}},{"t": 150,"i": {"START": false,"STOP": false},"o": {"MOTOR": true}},{"t": 300,"i": {"START": false,"STOP": false},"o": {"MOTOR": true}},{"t": 450,"i": {"START": false,"STOP": false},"o": {"MOTOR": true}},{"t": 600,"i": {"START": false,"STOP": false},"o": {"MOTOR": true}},{"t": 750,"i": {"START": false,"STOP": false},"o": {"MOTOR": true}},{"t": 900,"i": {"START": false,"STOP": true},"o": {"MOTOR": false}},{"t": 1050,"i": {"START": false,"STOP": false},"o": {"MOTOR": false}},{"t": 1200,"i": {"START": false,"STOP": false},"o": {"MOTOR": false}},{"t": 1350,"i": {"START": false,"STOP": false},"o": {"MOTOR": false}},{"t": 1500,"i": {"START": false,"STOP": false},"o": {"MOTOR": false}}]}},"fwd_rev": {"title": "정역 운전(인터락)","st": "MOTOR_FWD := ((FWD_PB AND NOT REV_PB AND NOT STOP) OR MOTOR_FWD) AND NOT ((STOP OR REV_PB)) AND NOT MOTOR_REV;\nMOTOR_REV := ((REV_PB AND NOT FWD_PB AND NOT STOP) OR MOTOR_REV) AND NOT ((STOP OR FWD_PB)) AND NOT MOTOR_FWD;","ladder": {"title": "정역 운전(인터락)","rungs": [{"comment": "","input_branches": [{"elements": [{"element_type": "CONTACT_NO","symbol": "FWD_PB","address": "","description": ""},{"element_type": "CONTACT_NC","symbol": "MOTOR_REV","address": "","description": ""},{"element_type": "CONTACT_NC","symbol": "REV_PB","address": "","description": ""},{"element_type": "CONTACT_NC","symbol": "STOP","address": "","description": ""}]},{"elements": [{"element_type": "CONTACT_NO","symbol": "MOTOR_FWD","address": "","description": ""},{"element_type": "CONTACT_NC","symbol": "MOTOR_REV","address": "","description": ""},{"element_type": "CONTACT_NC","symbol": "REV_PB","address": "","description": ""},{"element_type": "CONTACT_NC","symbol": "STOP","address": "","description": ""}]}],"outputs": [{"element_type": "COIL","symbol": "MOTOR_FWD","address": "","description": ""}]},{"comment": "","input_branches": [{"elements": [{"element_type": "CONTACT_NC","symbol": "FWD_PB","address": "","description": ""},{"element_type": "CONTACT_NC","symbol": "MOTOR_FWD","address": "","description": ""},{"element_type": "CONTACT_NO","symbol": "REV_PB","address": "","description": ""},{"element_type": "CONTACT_NC","symbol": "STOP","address": "","description": ""}]},{"elements": [{"element_type": "CONTACT_NC","symbol": "FWD_PB","address": "","description": ""},{"element_type": "CONTACT_NC","symbol": "MOTOR_FWD","address": "","description": ""},{"element_type": "CONTACT_NO","symbol": "MOTOR_REV","address": "","description": ""},{"element_type": "CONTACT_NC","symbol": "STOP","address": "","description": ""}]}],"outputs": [{"element_type": "COIL","symbol": "MOTOR_REV","address": "","description": ""}]}]},"explain": "## 이 장치는 무엇을 하나요\n■ 정역 운전(인터락)\n입력(사람·센서 신호): FWD_PB(정방향 버튼), REV_PB(역방향 버튼), STOP(정지)\n출력(움직이는 것): MOTOR_FWD(정방향 모터), MOTOR_REV(역방향 모터)\n로직 잠금(소프트웨어): MOTOR_FWD 와 MOTOR_REV 는 동시에 켜지지 않습니다 (정/역 동시 구동 금지). ※ 안전이 필요하면 기계식/하드와이어 인터록도 함께 두세요.\n\n## 동작 설명 (한 줄씩)\n- 렁 1: (FWD_PB가 켜져 있음, MOTOR_REV가 꺼져 있음, REV_PB가 꺼져 있음, STOP가 꺼져 있음) 또는 (MOTOR_FWD가 켜져 있음, MOTOR_REV가 꺼져 있음, REV_PB가 꺼져 있음, STOP가 꺼져 있음) 면 MOTOR_FWD가 켜집니다. (자기유지: 한 번 켜지면 정지 조건 전까지 유지)\n- 렁 2: (FWD_PB가 꺼져 있음, MOTOR_FWD가 꺼져 있음, REV_PB가 켜져 있음, STOP가 꺼져 있음) 또는 (FWD_PB가 꺼져 있음, MOTOR_FWD가 꺼져 있음, MOTOR_REV가 켜져 있음, STOP가 꺼져 있음) 면 MOTOR_REV가 켜집니다. (자기유지: 한 번 켜지면 정지 조건 전까지 유지)\n\n## 안전·검증\n- ✅ 로직 검사 통과 — 이중 코일·인터록 로직·도달성에 문제가 없습니다.\n- ℹ️ 이는 로직 검사이며 기능 안전 인증이 아닙니다. E-stop·가드 등 안전기능은 하드와이어로 구현하세요.","passed": true,"sim": {"inputs": ["FWD_PB","REV_PB","STOP"],"outputs": ["MOTOR_FWD","MOTOR_REV"],"samples": [{"t": 0,"i": {"FWD_PB": true,"REV_PB": false,"STOP": false},"o": {"MOTOR_FWD": true,"MOTOR_REV": false}},{"t": 150,"i": {"FWD_PB": false,"REV_PB": false,"STOP": false},"o": {"MOTOR_FWD": true,"MOTOR_REV": false}},{"t": 300,"i": {"FWD_PB": false,"REV_PB": false,"STOP": false},"o": {"MOTOR_FWD": true,"MOTOR_REV": false}},{"t": 450,"i": {"FWD_PB": false,"REV_PB": false,"STOP": false},"o": {"MOTOR_FWD": true,"MOTOR_REV": false}},{"t": 600,"i": {"FWD_PB": false,"REV_PB": false,"STOP": false},"o": {"MOTOR_FWD": true,"MOTOR_REV": false}},{"t": 750,"i": {"FWD_PB": false,"REV_PB": false,"STOP": false},"o": {"MOTOR_FWD": true,"MOTOR_REV": false}},{"t": 900,"i": {"FWD_PB": false,"REV_PB": true,"STOP": false},"o": {"MOTOR_FWD": false,"MOTOR_REV": true}},{"t": 1050,"i": {"FWD_PB": false,"REV_PB": false,"STOP": false},"o": {"MOTOR_FWD": false,"MOTOR_REV": true}},{"t": 1200,"i": {"FWD_PB": false,"REV_PB": false,"STOP": false},"o": {"MOTOR_FWD": false,"MOTOR_REV": true}},{"t": 1350,"i": {"FWD_PB": false,"REV_PB": false,"STOP": false},"o": {"MOTOR_FWD": false,"MOTOR_REV": true}},{"t": 1500,"i": {"FWD_PB": false,"REV_PB": false,"STOP": false},"o": {"MOTOR_FWD": false,"MOTOR_REV": true}}]}},"car_wash": {"title": "세차 순차 제어","st": "// 타이머 T0 (TON, 1000ms)\nT0(IN := SOAP, PT := T#1s);\n// 타이머 T1 (TON, 1000ms)\nT1(IN := RINSE, PT := T#1s);\n// 타이머 T2 (TON, 1000ms)\nT2(IN := DRY, PT := T#1s);\n\nSOAP := ((START AND NOT STOP AND NOT SOAP AND NOT RINSE AND NOT DRY) OR SOAP) AND NOT ((STOP) OR (T0.Q AND NOT STOP));\nRINSE := ((T0.Q AND NOT STOP) OR RINSE) AND NOT ((STOP) OR (T1.Q AND NOT STOP));\nDRY := ((T1.Q AND NOT STOP) OR DRY) AND NOT ((STOP) OR (T2.Q));","ladder": {"title": "세차 순차 제어","rungs": [{"comment": "타이머 T0 (TON, 1000ms)","input_branches": [{"elements": [{"element_type": "CONTACT_NO","symbol": "SOAP","address": "","description": ""}]}],"outputs": [{"element_type": "TIMER","symbol": "T0","address": "","description": "T#1s"}]},{"comment": "타이머 T1 (TON, 1000ms)","input_branches": [{"elements": [{"element_type": "CONTACT_NO","symbol": "RINSE","address": "","description": ""}]}],"outputs": [{"element_type": "TIMER","symbol": "T1","address": "","description": "T#1s"}]},{"comment": "타이머 T2 (TON, 1000ms)","input_branches": [{"elements": [{"element_type": "CONTACT_NO","symbol": "DRY","address": "","description": ""}]}],"outputs": [{"element_type": "TIMER","symbol": "T2","address": "","description": "T#1s"}]},{"comment": "","input_branches": [{"elements": [{"element_type": "CONTACT_NC","symbol": "DRY","address": "","description": ""},{"element_type": "CONTACT_NC","symbol": "RINSE","address": "","description": ""},{"element_type": "CONTACT_NC","symbol": "SOAP","address": "","description": ""},{"element_type": "CONTACT_NO","symbol": "START","address": "","description": ""},{"element_type": "CONTACT_NC","symbol": "STOP","address": "","description": ""},{"element_type": "CONTACT_NC","symbol": "T0.Q","address": "","description": ""}]},{"elements": [{"element_type": "CONTACT_NO","symbol": "SOAP","address": "","description": ""},{"element_type": "CONTACT_NC","symbol": "STOP","address": "","description": ""},{"element_type": "CONTACT_NC","symbol": "T0.Q","address": "","description": ""}]}],"outputs": [{"element_type": "COIL","symbol": "SOAP","address": "","description": ""}]},{"comment": "","input_branches": [{"elements": [{"element_type": "CONTACT_NC","symbol": "STOP","address": "","description": ""},{"element_type": "CONTACT_NO","symbol": "T0.Q","address": "","description": ""},{"element_type": "CONTACT_NC","symbol": "T1.Q","address": "","description": ""}]},{"elements": [{"element_type": "CONTACT_NO","symbol": "RINSE","address": "","description": ""},{"element_type": "CONTACT_NC","symbol": "STOP","address": "","description": ""},{"element_type": "CONTACT_NC","symbol": "T1.Q","address": "","description": ""}]}],"outputs": [{"element_type": "COIL","symbol": "RINSE","address": "","description": ""}]},{"comment": "","input_branches": [{"elements": [{"element_type": "CONTACT_NC","symbol": "STOP","address": "","description": ""},{"element_type": "CONTACT_NO","symbol": "T1.Q","address": "","description": ""},{"element_type": "CONTACT_NC","symbol": "T2.Q","address": "","description": ""}]},{"elements": [{"element_type": "CONTACT_NO","symbol": "DRY","address": "","description": ""},{"element_type": "CONTACT_NC","symbol": "STOP","address": "","description": ""},{"element_type": "CONTACT_NC","symbol": "T2.Q","address": "","description": ""}]}],"outputs": [{"element_type": "COIL","symbol": "DRY","address": "","description": ""}]}]},"explain": "## 이 장치는 무엇을 하나요\n■ 세차 순차 제어\n입력(사람·센서 신호): START(기동), STOP(정지)\n출력(움직이는 것): SOAP(1단계), RINSE(2단계), DRY(3단계)\n타이머 T0: 조건이 유지되면 1초 뒤 신호를 냅니다.\n타이머 T1: 조건이 유지되면 1초 뒤 신호를 냅니다.\n타이머 T2: 조건이 유지되면 1초 뒤 신호를 냅니다.\n\n## 동작 설명 (한 줄씩)\n- 렁 1: SOAP가 켜져 있음 동안 타이머 T0(T#1s)가 동작합니다.\n- 렁 2: RINSE가 켜져 있음 동안 타이머 T1(T#1s)가 동작합니다.\n- 렁 3: DRY가 켜져 있음 동안 타이머 T2(T#1s)가 동작합니다.\n- 렁 4: (DRY가 꺼져 있음, RINSE가 꺼져 있음, SOAP가 꺼져 있음, START가 켜져 있음, STOP가 꺼져 있음, T0.Q가 꺼져 있음) 또는 (SOAP가 켜져 있음, STOP가 꺼져 있음, T0.Q가 꺼져 있음) 면 SOAP가 켜집니다. (자기유지: 한 번 켜지면 정지 조건 전까지 유지)\n- 렁 5: (STOP가 꺼져 있음, T0.Q가 켜져 있음, T1.Q가 꺼져 있음) 또는 (RINSE가 켜져 있음, STOP가 꺼져 있음, T1.Q가 꺼져 있음) 면 RINSE가 켜집니다. (자기유지: 한 번 켜지면 정지 조건 전까지 유지)\n- 렁 6: (STOP가 꺼져 있음, T1.Q가 켜져 있음, T2.Q가 꺼져 있음) 또는 (DRY가 켜져 있음, STOP가 꺼져 있음, T2.Q가 꺼져 있음) 면 DRY가 켜집니다. (자기유지: 한 번 켜지면 정지 조건 전까지 유지)\n\n## 안전·검증\n- ✅ 로직 검사 통과 — 이중 코일·인터록 로직·도달성에 문제가 없습니다.\n- ℹ️ 이는 로직 검사이며 기능 안전 인증이 아닙니다. E-stop·가드 등 안전기능은 하드와이어로 구현하세요.","passed": true,"sim": {"inputs": ["START","STOP"],"outputs": ["SOAP","RINSE","DRY"],"samples": [{"t": 0,"i": {"START": true,"STOP": false},"o": {"SOAP": true,"RINSE": false,"DRY": false}},{"t": 150,"i": {"START": false,"STOP": false},"o": {"SOAP": true,"RINSE": false,"DRY": false}},{"t": 300,"i": {"START": false,"STOP": false},"o": {"SOAP": true,"RINSE": false,"DRY": false}},{"t": 450,"i": {"START": false,"STOP": false},"o": {"SOAP": true,"RINSE": false,"DRY": false}},{"t": 600,"i": {"START": false,"STOP": false},"o": {"SOAP": true,"RINSE": false,"DRY": false}},{"t": 750,"i": {"START": false,"STOP": false},"o": {"SOAP": true,"RINSE": false,"DRY": false}},{"t": 900,"i": {"START": false,"STOP": false},"o": {"SOAP": true,"RINSE": false,"DRY": false}},{"t": 1050,"i": {"START": false,"STOP": false},"o": {"SOAP": false,"RINSE": true,"DRY": false}},{"t": 1200,"i": {"START": false,"STOP": false},"o": {"SOAP": false,"RINSE": true,"DRY": false}},{"t": 1350,"i": {"START": false,"STOP": false},"o": {"SOAP": false,"RINSE": true,"DRY": false}},{"t": 1500,"i": {"START": false,"STOP": false},"o": {"SOAP": false,"RINSE": true,"DRY": false}},{"t": 1650,"i": {"START": false,"STOP": false},"o": {"SOAP": false,"RINSE": true,"DRY": false}},{"t": 1800,"i": {"START": false,"STOP": false},"o": {"SOAP": false,"RINSE": true,"DRY": false}},{"t": 1950,"i": {"START": false,"STOP": false},"o": {"SOAP": false,"RINSE": true,"DRY": false}},{"t": 2100,"i": {"START": false,"STOP": false},"o": {"SOAP": false,"RINSE": false,"DRY": true}},{"t": 2250,"i": {"START": false,"STOP": false},"o": {"SOAP": false,"RINSE": false,"DRY": true}},{"t": 2400,"i": {"START": false,"STOP": false},"o": {"SOAP": false,"RINSE": false,"DRY": true}},{"t": 2550,"i": {"START": false,"STOP": false},"o": {"SOAP": false,"RINSE": false,"DRY": true}},{"t": 2700,"i": {"START": false,"STOP": false},"o": {"SOAP": false,"RINSE": false,"DRY": true}},{"t": 2850,"i": {"START": false,"STOP": false},"o": {"SOAP": false,"RINSE": false,"DRY": true}},{"t": 3000,"i": {"START": false,"STOP": false},"o": {"SOAP": false,"RINSE": false,"DRY": true}},{"t": 3150,"i": {"START": false,"STOP": false},"o": {"SOAP": false,"RINSE": false,"DRY": false}},{"t": 3300,"i": {"START": false,"STOP": false},"o": {"SOAP": false,"RINSE": false,"DRY": false}},{"t": 3450,"i": {"START": false,"STOP": false},"o": {"SOAP": false,"RINSE": false,"DRY": false}},{"t": 3600,"i": {"START": false,"STOP": false},"o": {"SOAP": false,"RINSE": false,"DRY": false}}]}},"count_eject": {"title": "부품 카운터(10개 배출)","st": "// 카운터 C1 (CTU, PV=10)\nC1(CU := PART_SENSOR, R := RESET_PB, PV := 10);\n\nEJECT := ((C1.Q AND NOT RESET_PB) OR EJECT) AND NOT ((RESET_PB));","ladder": {"title": "부품 카운터(10개 배출)","rungs": [{"comment": "카운터 C1 (CTU, PV=10)","input_branches": [{"elements": [{"element_type": "CONTACT_NO","symbol": "PART_SENSOR","address": "","description": ""}]}],"outputs": [{"element_type": "COUNTER","symbol": "C1","address": "","description": "10"}]},{"comment": "C1 리셋","input_branches": [{"elements": [{"element_type": "CONTACT_NO","symbol": "RESET_PB","address": "","description": ""}]}],"outputs": [{"element_type": "COIL_RESET","symbol": "C1","address": "","description": ""}]},{"comment": "","input_branches": [{"elements": [{"element_type": "CONTACT_NO","symbol": "C1.Q","address": "","description": ""},{"element_type": "CONTACT_NC","symbol": "RESET_PB","address": "","description": ""}]},{"elements": [{"element_type": "CONTACT_NO","symbol": "EJECT","address": "","description": ""},{"element_type": "CONTACT_NC","symbol": "RESET_PB","address": "","description": ""}]}],"outputs": [{"element_type": "COIL","symbol": "EJECT","address": "","description": ""}]}]},"explain": "## 이 장치는 무엇을 하나요\n■ 부품 카운터(10개 배출)\n입력(사람·센서 신호): PART_SENSOR(부품 감지), RESET_PB(리셋)\n출력(움직이는 것): EJECT(배출)\n카운터 C1: 신호를 10번 세면 완료됩니다.\n\n## 동작 설명 (한 줄씩)\n- 렁 1: PART_SENSOR가 켜져 있음 마다 카운터 C1가 1씩 셉니다.\n- 렁 2: RESET_PB가 켜져 있음 면 C1가 켜집니다.\n- 렁 3: (C1.Q가 켜져 있음, RESET_PB가 꺼져 있음) 또는 (EJECT가 켜져 있음, RESET_PB가 꺼져 있음) 면 EJECT가 켜집니다. (자기유지: 한 번 켜지면 정지 조건 전까지 유지)\n\n## 안전·검증\n- ✅ 로직 검사 통과 — 이중 코일·인터록 로직·도달성에 문제가 없습니다.\n- ℹ️ 이는 로직 검사이며 기능 안전 인증이 아닙니다. E-stop·가드 등 안전기능은 하드와이어로 구현하세요.","passed": true,"sim": {"inputs": ["PART_SENSOR","RESET_PB"],"outputs": ["EJECT"],"samples": [{"t": 0,"i": {"PART_SENSOR": false,"RESET_PB": false},"o": {"EJECT": false}},{"t": 200,"i": {"PART_SENSOR": false,"RESET_PB": false},"o": {"EJECT": false}},{"t": 400,"i": {"PART_SENSOR": true,"RESET_PB": false},"o": {"EJECT": false}},{"t": 600,"i": {"PART_SENSOR": false,"RESET_PB": false},"o": {"EJECT": false}},{"t": 800,"i": {"PART_SENSOR": false,"RESET_PB": false},"o": {"EJECT": false}},{"t": 1000,"i": {"PART_SENSOR": true,"RESET_PB": false},"o": {"EJECT": false}},{"t": 1200,"i": {"PART_SENSOR": false,"RESET_PB": false},"o": {"EJECT": false}},{"t": 1400,"i": {"PART_SENSOR": false,"RESET_PB": false},"o": {"EJECT": false}},{"t": 1600,"i": {"PART_SENSOR": true,"RESET_PB": false},"o": {"EJECT": false}},{"t": 1800,"i": {"PART_SENSOR": false,"RESET_PB": false},"o": {"EJECT": false}},{"t": 2000,"i": {"PART_SENSOR": false,"RESET_PB": false},"o": {"EJECT": false}},{"t": 2200,"i": {"PART_SENSOR": true,"RESET_PB": false},"o": {"EJECT": false}},{"t": 2400,"i": {"PART_SENSOR": false,"RESET_PB": false},"o": {"EJECT": false}},{"t": 2600,"i": {"PART_SENSOR": false,"RESET_PB": false},"o": {"EJECT": false}},{"t": 2800,"i": {"PART_SENSOR": true,"RESET_PB": false},"o": {"EJECT": false}},{"t": 3000,"i": {"PART_SENSOR": false,"RESET_PB": false},"o": {"EJECT": false}},{"t": 3200,"i": {"PART_SENSOR": false,"RESET_PB": false},"o": {"EJECT": false}},{"t": 3400,"i": {"PART_SENSOR": true,"RESET_PB": false},"o": {"EJECT": false}},{"t": 3600,"i": {"PART_SENSOR": false,"RESET_PB": false},"o": {"EJECT": false}},{"t": 3800,"i": {"PART_SENSOR": false,"RESET_PB": false},"o": {"EJECT": false}},{"t": 4000,"i": {"PART_SENSOR": true,"RESET_PB": false},"o": {"EJECT": false}},{"t": 4200,"i": {"PART_SENSOR": false,"RESET_PB": false},"o": {"EJECT": false}},{"t": 4400,"i": {"PART_SENSOR": false,"RESET_PB": false},"o": {"EJECT": false}},{"t": 4600,"i": {"PART_SENSOR": true,"RESET_PB": false},"o": {"EJECT": false}},{"t": 4800,"i": {"PART_SENSOR": false,"RESET_PB": false},"o": {"EJECT": false}},{"t": 5000,"i": {"PART_SENSOR": false,"RESET_PB": false},"o": {"EJECT": false}},{"t": 5200,"i": {"PART_SENSOR": true,"RESET_PB": false},"o": {"EJECT": false}},{"t": 5400,"i": {"PART_SENSOR": false,"RESET_PB": false},"o": {"EJECT": false}},{"t": 5600,"i": {"PART_SENSOR": false,"RESET_PB": false},"o": {"EJECT": false}},{"t": 5800,"i": {"PART_SENSOR": true,"RESET_PB": false},"o": {"EJECT": true}},{"t": 6000,"i": {"PART_SENSOR": false,"RESET_PB": false},"o": {"EJECT": true}},{"t": 6200,"i": {"PART_SENSOR": false,"RESET_PB": false},"o": {"EJECT": true}},{"t": 6400,"i": {"PART_SENSOR": false,"RESET_PB": false},"o": {"EJECT": true}},{"t": 6600,"i": {"PART_SENSOR": false,"RESET_PB": false},"o": {"EJECT": true}},{"t": 6800,"i": {"PART_SENSOR": false,"RESET_PB": false},"o": {"EJECT": true}},{"t": 7000,"i": {"PART_SENSOR": false,"RESET_PB": true},"o": {"EJECT": false}},{"t": 7200,"i": {"PART_SENSOR": false,"RESET_PB": true},"o": {"EJECT": false}},{"t": 7400,"i": {"PART_SENSOR": false,"RESET_PB": false},"o": {"EJECT": false}},{"t": 7600,"i": {"PART_SENSOR": false,"RESET_PB": false},"o": {"EJECT": false}},{"t": 7800,"i": {"PART_SENSOR": false,"RESET_PB": false},"o": {"EJECT": false}},{"t": 8000,"i": {"PART_SENSOR": false,"RESET_PB": false},"o": {"EJECT": false}}]}},"conveyor_divert": {"title": "컨베이어 분기(A/B 게이트 인터락)","st": "GATE_A := ((SEL_A AND NOT SEL_B AND NOT DIV_STOP) OR GATE_A) AND NOT ((DIV_STOP OR SEL_B)) AND NOT GATE_B;\nGATE_B := ((SEL_B AND NOT SEL_A AND NOT DIV_STOP) OR GATE_B) AND NOT ((DIV_STOP OR SEL_A)) AND NOT GATE_A;","ladder": {"title": "컨베이어 분기(A/B 게이트 인터락)","rungs": [{"comment": "","input_branches": [{"elements": [{"element_type": "CONTACT_NC","symbol": "DIV_STOP","address": "","description": ""},{"element_type": "CONTACT_NC","symbol": "GATE_B","address": "","description": ""},{"element_type": "CONTACT_NO","symbol": "SEL_A","address": "","description": ""},{"element_type": "CONTACT_NC","symbol": "SEL_B","address": "","description": ""}]},{"elements": [{"element_type": "CONTACT_NC","symbol": "DIV_STOP","address": "","description": ""},{"element_type": "CONTACT_NO","symbol": "GATE_A","address": "","description": ""},{"element_type": "CONTACT_NC","symbol": "GATE_B","address": "","description": ""},{"element_type": "CONTACT_NC","symbol": "SEL_B","address": "","description": ""}]}],"outputs": [{"element_type": "COIL","symbol": "GATE_A","address": "","description": ""}]},{"comment": "","input_branches": [{"elements": [{"element_type": "CONTACT_NC","symbol": "DIV_STOP","address": "","description": ""},{"element_type": "CONTACT_NC","symbol": "GATE_A","address": "","description": ""},{"element_type": "CONTACT_NC","symbol": "SEL_A","address": "","description": ""},{"element_type": "CONTACT_NO","symbol": "SEL_B","address": "","description": ""}]},{"elements": [{"element_type": "CONTACT_NC","symbol": "DIV_STOP","address": "","description": ""},{"element_type": "CONTACT_NC","symbol": "GATE_A","address": "","description": ""},{"element_type": "CONTACT_NO","symbol": "GATE_B","address": "","description": ""},{"element_type": "CONTACT_NC","symbol": "SEL_A","address": "","description": ""}]}],"outputs": [{"element_type": "COIL","symbol": "GATE_B","address": "","description": ""}]}]},"explain": "## 이 장치는 무엇을 하나요\n■ 컨베이어 분기(A/B 게이트 인터락)\n입력(사람·센서 신호): SEL_A(A 라인 선택), SEL_B(B 라인 선택), DIV_STOP(정지)\n출력(움직이는 것): GATE_A(A 분기 게이트), GATE_B(B 분기 게이트)\n로직 잠금(소프트웨어): GATE_A 와 GATE_B 는 동시에 켜지지 않습니다 (A/B 분기 게이트 동시 작동 금지). ※ 안전이 필요하면 기계식/하드와이어 인터록도 함께 두세요.\n\n## 동작 설명 (한 줄씩)\n- 렁 1: (DIV_STOP가 꺼져 있음, GATE_B가 꺼져 있음, SEL_A가 켜져 있음, SEL_B가 꺼져 있음) 또는 (DIV_STOP가 꺼져 있음, GATE_A가 켜져 있음, GATE_B가 꺼져 있음, SEL_B가 꺼져 있음) 면 GATE_A가 켜집니다. (자기유지: 한 번 켜지면 정지 조건 전까지 유지)\n- 렁 2: (DIV_STOP가 꺼져 있음, GATE_A가 꺼져 있음, SEL_A가 꺼져 있음, SEL_B가 켜져 있음) 또는 (DIV_STOP가 꺼져 있음, GATE_A가 꺼져 있음, GATE_B가 켜져 있음, SEL_A가 꺼져 있음) 면 GATE_B가 켜집니다. (자기유지: 한 번 켜지면 정지 조건 전까지 유지)\n\n## 안전·검증\n- ✅ 로직 검사 통과 — 이중 코일·인터록 로직·도달성에 문제가 없습니다.\n- ℹ️ 이는 로직 검사이며 기능 안전 인증이 아닙니다. E-stop·가드 등 안전기능은 하드와이어로 구현하세요.","passed": true,"sim": {"inputs": ["DIV_STOP","SEL_A","SEL_B"],"outputs": ["GATE_A","GATE_B"],"samples": [{"t": 0,"i": {"DIV_STOP": false,"SEL_A": false,"SEL_B": false},"o": {"GATE_A": false,"GATE_B": false}},{"t": 200,"i": {"DIV_STOP": false,"SEL_A": true,"SEL_B": false},"o": {"GATE_A": true,"GATE_B": false}},{"t": 400,"i": {"DIV_STOP": false,"SEL_A": true,"SEL_B": false},"o": {"GATE_A": true,"GATE_B": false}},{"t": 600,"i": {"DIV_STOP": false,"SEL_A": false,"SEL_B": false},"o": {"GATE_A": true,"GATE_B": false}},{"t": 800,"i": {"DIV_STOP": false,"SEL_A": false,"SEL_B": false},"o": {"GATE_A": true,"GATE_B": false}},{"t": 1000,"i": {"DIV_STOP": false,"SEL_A": false,"SEL_B": false},"o": {"GATE_A": true,"GATE_B": false}},{"t": 1200,"i": {"DIV_STOP": false,"SEL_A": false,"SEL_B": false},"o": {"GATE_A": true,"GATE_B": false}},{"t": 1400,"i": {"DIV_STOP": false,"SEL_A": false,"SEL_B": false},"o": {"GATE_A": true,"GATE_B": false}},{"t": 1600,"i": {"DIV_STOP": false,"SEL_A": false,"SEL_B": false},"o": {"GATE_A": true,"GATE_B": false}},{"t": 1800,"i": {"DIV_STOP": false,"SEL_A": false,"SEL_B": false},"o": {"GATE_A": true,"GATE_B": false}},{"t": 2000,"i": {"DIV_STOP": false,"SEL_A": false,"SEL_B": true},"o": {"GATE_A": false,"GATE_B": true}},{"t": 2200,"i": {"DIV_STOP": false,"SEL_A": false,"SEL_B": true},"o": {"GATE_A": false,"GATE_B": true}},{"t": 2400,"i": {"DIV_STOP": false,"SEL_A": false,"SEL_B": false},"o": {"GATE_A": false,"GATE_B": true}},{"t": 2600,"i": {"DIV_STOP": false,"SEL_A": false,"SEL_B": false},"o": {"GATE_A": false,"GATE_B": true}},{"t": 2800,"i": {"DIV_STOP": false,"SEL_A": false,"SEL_B": false},"o": {"GATE_A": false,"GATE_B": true}},{"t": 3000,"i": {"DIV_STOP": false,"SEL_A": false,"SEL_B": false},"o": {"GATE_A": false,"GATE_B": true}},{"t": 3200,"i": {"DIV_STOP": false,"SEL_A": false,"SEL_B": false},"o": {"GATE_A": false,"GATE_B": true}},{"t": 3400,"i": {"DIV_STOP": false,"SEL_A": false,"SEL_B": false},"o": {"GATE_A": false,"GATE_B": true}},{"t": 3600,"i": {"DIV_STOP": false,"SEL_A": false,"SEL_B": false},"o": {"GATE_A": false,"GATE_B": true}},{"t": 3800,"i": {"DIV_STOP": false,"SEL_A": false,"SEL_B": false},"o": {"GATE_A": false,"GATE_B": true}},{"t": 4000,"i": {"DIV_STOP": false,"SEL_A": false,"SEL_B": false},"o": {"GATE_A": false,"GATE_B": true}},{"t": 4200,"i": {"DIV_STOP": true,"SEL_A": false,"SEL_B": false},"o": {"GATE_A": false,"GATE_B": false}},{"t": 4400,"i": {"DIV_STOP": true,"SEL_A": false,"SEL_B": false},"o": {"GATE_A": false,"GATE_B": false}},{"t": 4600,"i": {"DIV_STOP": false,"SEL_A": false,"SEL_B": false},"o": {"GATE_A": false,"GATE_B": false}},{"t": 4800,"i": {"DIV_STOP": false,"SEL_A": false,"SEL_B": false},"o": {"GATE_A": false,"GATE_B": false}},{"t": 5000,"i": {"DIV_STOP": false,"SEL_A": false,"SEL_B": false},"o": {"GATE_A": false,"GATE_B": false}},{"t": 5200,"i": {"DIV_STOP": false,"SEL_A": false,"SEL_B": false},"o": {"GATE_A": false,"GATE_B": false}},{"t": 5400,"i": {"DIV_STOP": false,"SEL_A": false,"SEL_B": false},"o": {"GATE_A": false,"GATE_B": false}},{"t": 5600,"i": {"DIV_STOP": false,"SEL_A": false,"SEL_B": false},"o": {"GATE_A": false,"GATE_B": false}},{"t": 5800,"i": {"DIV_STOP": false,"SEL_A": false,"SEL_B": false},"o": {"GATE_A": false,"GATE_B": false}},{"t": 6000,"i": {"DIV_STOP": false,"SEL_A": false,"SEL_B": false},"o": {"GATE_A": false,"GATE_B": false}}]}},"weld_cell": {"title": "용접 셀 사이클(클램프→용접→해제)","st": "// 타이머 T0 (TON, 3000ms)\nT0(IN := CLAMP, PT := T#3s);\n// 타이머 T1 (TON, 5000ms)\nT1(IN := WELD, PT := T#5s);\n// 타이머 T2 (TON, 3000ms)\nT2(IN := UNCLAMP, PT := T#3s);\n\nCLAMP := ((WELD_START AND NOT WELD_STOP AND NOT CLAMP AND NOT WELD AND NOT UNCLAMP) OR CLAMP) AND NOT ((WELD_STOP) OR (T0.Q AND NOT WELD_STOP));\nWELD := ((T0.Q AND NOT WELD_STOP) OR WELD) AND NOT ((WELD_STOP) OR (T1.Q AND NOT WELD_STOP));\nUNCLAMP := ((T1.Q AND NOT WELD_STOP) OR UNCLAMP) AND NOT ((WELD_STOP) OR (T2.Q));","ladder": {"title": "용접 셀 사이클(클램프→용접→해제)","rungs": [{"comment": "타이머 T0 (TON, 3000ms)","input_branches": [{"elements": [{"element_type": "CONTACT_NO","symbol": "CLAMP","address": "","description": ""}]}],"outputs": [{"element_type": "TIMER","symbol": "T0","address": "","description": "T#3s"}]},{"comment": "타이머 T1 (TON, 5000ms)","input_branches": [{"elements": [{"element_type": "CONTACT_NO","symbol": "WELD","address": "","description": ""}]}],"outputs": [{"element_type": "TIMER","symbol": "T1","address": "","description": "T#5s"}]},{"comment": "타이머 T2 (TON, 3000ms)","input_branches": [{"elements": [{"element_type": "CONTACT_NO","symbol": "UNCLAMP","address": "","description": ""}]}],"outputs": [{"element_type": "TIMER","symbol": "T2","address": "","description": "T#3s"}]},{"comment": "","input_branches": [{"elements": [{"element_type": "CONTACT_NC","symbol": "CLAMP","address": "","description": ""},{"element_type": "CONTACT_NC","symbol": "T0.Q","address": "","description": ""},{"element_type": "CONTACT_NC","symbol": "UNCLAMP","address": "","description": ""},{"element_type": "CONTACT_NC","symbol": "WELD","address": "","description": ""},{"element_type": "CONTACT_NO","symbol": "WELD_START","address": "","description": ""},{"element_type": "CONTACT_NC","symbol": "WELD_STOP","address": "","description": ""}]},{"elements": [{"element_type": "CONTACT_NO","symbol": "CLAMP","address": "","description": ""},{"element_type": "CONTACT_NC","symbol": "T0.Q","address": "","description": ""},{"element_type": "CONTACT_NC","symbol": "WELD_STOP","address": "","description": ""}]}],"outputs": [{"element_type": "COIL","symbol": "CLAMP","address": "","description": ""}]},{"comment": "","input_branches": [{"elements": [{"element_type": "CONTACT_NO","symbol": "T0.Q","address": "","description": ""},{"element_type": "CONTACT_NC","symbol": "T1.Q","address": "","description": ""},{"element_type": "CONTACT_NC","symbol": "WELD_STOP","address": "","description": ""}]},{"elements": [{"element_type": "CONTACT_NC","symbol": "T1.Q","address": "","description": ""},{"element_type": "CONTACT_NO","symbol": "WELD","address": "","description": ""},{"element_type": "CONTACT_NC","symbol": "WELD_STOP","address": "","description": ""}]}],"outputs": [{"element_type": "COIL","symbol": "WELD","address": "","description": ""}]},{"comment": "","input_branches": [{"elements": [{"element_type": "CONTACT_NO","symbol": "T1.Q","address": "","description": ""},{"element_type": "CONTACT_NC","symbol": "T2.Q","address": "","description": ""},{"element_type": "CONTACT_NC","symbol": "WELD_STOP","address": "","description": ""}]},{"elements": [{"element_type": "CONTACT_NC","symbol": "T2.Q","address": "","description": ""},{"element_type": "CONTACT_NO","symbol": "UNCLAMP","address": "","description": ""},{"element_type": "CONTACT_NC","symbol": "WELD_STOP","address": "","description": ""}]}],"outputs": [{"element_type": "COIL","symbol": "UNCLAMP","address": "","description": ""}]}]},"explain": "## 이 장치는 무엇을 하나요\n■ 용접 셀 사이클(클램프→용접→해제)\n입력(사람·센서 신호): WELD_START(기동), WELD_STOP(정지)\n출력(움직이는 것): CLAMP(1단계), WELD(2단계), UNCLAMP(3단계)\n타이머 T0: 조건이 유지되면 3초 뒤 신호를 냅니다.\n타이머 T1: 조건이 유지되면 5초 뒤 신호를 냅니다.\n타이머 T2: 조건이 유지되면 3초 뒤 신호를 냅니다.\n\n## 동작 설명 (한 줄씩)\n- 렁 1: CLAMP가 켜져 있음 동안 타이머 T0(T#3s)가 동작합니다.\n- 렁 2: WELD가 켜져 있음 동안 타이머 T1(T#5s)가 동작합니다.\n- 렁 3: UNCLAMP가 켜져 있음 동안 타이머 T2(T#3s)가 동작합니다.\n- 렁 4: (CLAMP가 꺼져 있음, T0.Q가 꺼져 있음, UNCLAMP가 꺼져 있음, WELD가 꺼져 있음, WELD_START가 켜져 있음, WELD_STOP가 꺼져 있음) 또는 (CLAMP가 켜져 있음, T0.Q가 꺼져 있음, WELD_STOP가 꺼져 있음) 면 CLAMP가 켜집니다. (자기유지: 한 번 켜지면 정지 조건 전까지 유지)\n- 렁 5: (T0.Q가 켜져 있음, T1.Q가 꺼져 있음, WELD_STOP가 꺼져 있음) 또는 (T1.Q가 꺼져 있음, WELD가 켜져 있음, WELD_STOP가 꺼져 있음) 면 WELD가 켜집니다. (자기유지: 한 번 켜지면 정지 조건 전까지 유지)\n- 렁 6: (T1.Q가 켜져 있음, T2.Q가 꺼져 있음, WELD_STOP가 꺼져 있음) 또는 (T2.Q가 꺼져 있음, UNCLAMP가 켜져 있음, WELD_STOP가 꺼져 있음) 면 UNCLAMP가 켜집니다. (자기유지: 한 번 켜지면 정지 조건 전까지 유지)\n\n## 안전·검증\n- ✅ 로직 검사 통과 — 이중 코일·인터록 로직·도달성에 문제가 없습니다.\n- ℹ️ 이는 로직 검사이며 기능 안전 인증이 아닙니다. E-stop·가드 등 안전기능은 하드와이어로 구현하세요.","passed": true,"sim": {"inputs": ["WELD_START","WELD_STOP"],"outputs": ["CLAMP","WELD","UNCLAMP"],"samples": [{"t": 0,"i": {"WELD_START": false,"WELD_STOP": false},"o": {"CLAMP": false,"WELD": false,"UNCLAMP": false}},{"t": 400,"i": {"WELD_START": true,"WELD_STOP": false},"o": {"CLAMP": true,"WELD": false,"UNCLAMP": false}},{"t": 800,"i": {"WELD_START": false,"WELD_STOP": false},"o": {"CLAMP": true,"WELD": false,"UNCLAMP": false}},{"t": 1200,"i": {"WELD_START": false,"WELD_STOP": false},"o": {"CLAMP": true,"WELD": false,"UNCLAMP": false}},{"t": 1600,"i": {"WELD_START": false,"WELD_STOP": false},"o": {"CLAMP": true,"WELD": false,"UNCLAMP": false}},{"t": 2000,"i": {"WELD_START": false,"WELD_STOP": false},"o": {"CLAMP": true,"WELD": false,"UNCLAMP": false}},{"t": 2400,"i": {"WELD_START": false,"WELD_STOP": false},"o": {"CLAMP": true,"WELD": false,"UNCLAMP": false}},{"t": 2800,"i": {"WELD_START": false,"WELD_STOP": false},"o": {"CLAMP": true,"WELD": false,"UNCLAMP": false}},{"t": 3200,"i": {"WELD_START": false,"WELD_STOP": false},"o": {"CLAMP": true,"WELD": false,"UNCLAMP": false}},{"t": 3600,"i": {"WELD_START": false,"WELD_STOP": false},"o": {"CLAMP": true,"WELD": false,"UNCLAMP": false}},{"t": 4000,"i": {"WELD_START": false,"WELD_STOP": false},"o": {"CLAMP": false,"WELD": true,"UNCLAMP": false}},{"t": 4400,"i": {"WELD_START": false,"WELD_STOP": false},"o": {"CLAMP": false,"WELD": true,"UNCLAMP": false}},{"t": 4800,"i": {"WELD_START": false,"WELD_STOP": false},"o": {"CLAMP": false,"WELD": true,"UNCLAMP": false}},{"t": 5200,"i": {"WELD_START": false,"WELD_STOP": false},"o": {"CLAMP": false,"WELD": true,"UNCLAMP": false}},{"t": 5600,"i": {"WELD_START": false,"WELD_STOP": false},"o": {"CLAMP": false,"WELD": true,"UNCLAMP": false}},{"t": 6000,"i": {"WELD_START": false,"WELD_STOP": false},"o": {"CLAMP": false,"WELD": true,"UNCLAMP": false}},{"t": 6400,"i": {"WELD_START": false,"WELD_STOP": false},"o": {"CLAMP": false,"WELD": true,"UNCLAMP": false}},{"t": 6800,"i": {"WELD_START": false,"WELD_STOP": false},"o": {"CLAMP": false,"WELD": true,"UNCLAMP": false}},{"t": 7200,"i": {"WELD_START": false,"WELD_STOP": false},"o": {"CLAMP": false,"WELD": true,"UNCLAMP": false}},{"t": 7600,"i": {"WELD_START": false,"WELD_STOP": false},"o": {"CLAMP": false,"WELD": true,"UNCLAMP": false}},{"t": 8000,"i": {"WELD_START": false,"WELD_STOP": false},"o": {"CLAMP": false,"WELD": true,"UNCLAMP": false}},{"t": 8400,"i": {"WELD_START": false,"WELD_STOP": false},"o": {"CLAMP": false,"WELD": true,"UNCLAMP": false}},{"t": 8800,"i": {"WELD_START": false,"WELD_STOP": false},"o": {"CLAMP": false,"WELD": true,"UNCLAMP": false}},{"t": 9200,"i": {"WELD_START": false,"WELD_STOP": false},"o": {"CLAMP": false,"WELD": true,"UNCLAMP": false}},{"t": 9600,"i": {"WELD_START": false,"WELD_STOP": false},"o": {"CLAMP": false,"WELD": false,"UNCLAMP": true}},{"t": 10000,"i": {"WELD_START": false,"WELD_STOP": false},"o": {"CLAMP": false,"WELD": false,"UNCLAMP": true}},{"t": 10400,"i": {"WELD_START": false,"WELD_STOP": false},"o": {"CLAMP": false,"WELD": false,"UNCLAMP": true}},{"t": 10800,"i": {"WELD_START": false,"WELD_STOP": false},"o": {"CLAMP": false,"WELD": false,"UNCLAMP": true}},{"t": 11200,"i": {"WELD_START": false,"WELD_STOP": false},"o": {"CLAMP": false,"WELD": false,"UNCLAMP": true}},{"t": 11600,"i": {"WELD_START": false,"WELD_STOP": false},"o": {"CLAMP": false,"WELD": false,"UNCLAMP": true}},{"t": 12000,"i": {"WELD_START": false,"WELD_STOP": false},"o": {"CLAMP": false,"WELD": false,"UNCLAMP": true}}]}},"batch_fill_mix_drain": {"title": "배치 충전/교반/배출","st": "// 타이머 T0 (TON, 8000ms)\nT0(IN := FILL_VALVE, PT := T#8s);\n// 타이머 T1 (TON, 10000ms)\nT1(IN := MIXER, PT := T#10s);\n// 타이머 T2 (TON, 6000ms)\nT2(IN := DRAIN_VALVE, PT := T#6s);\n\nFILL_VALVE := ((START AND NOT STOP AND NOT FILL_VALVE AND NOT MIXER AND NOT DRAIN_VALVE) OR FILL_VALVE) AND NOT ((STOP) OR (T0.Q AND NOT STOP));\nMIXER := ((T0.Q AND NOT STOP) OR MIXER) AND NOT ((STOP) OR (T1.Q AND NOT STOP));\nDRAIN_VALVE := ((T1.Q AND NOT STOP) OR DRAIN_VALVE) AND NOT ((STOP) OR (T2.Q));","ladder": {"title": "배치 충전/교반/배출","rungs": [{"comment": "타이머 T0 (TON, 8000ms)","input_branches": [{"elements": [{"element_type": "CONTACT_NO","symbol": "FILL_VALVE","address": "","description": ""}]}],"outputs": [{"element_type": "TIMER","symbol": "T0","address": "","description": "T#8s"}]},{"comment": "타이머 T1 (TON, 10000ms)","input_branches": [{"elements": [{"element_type": "CONTACT_NO","symbol": "MIXER","address": "","description": ""}]}],"outputs": [{"element_type": "TIMER","symbol": "T1","address": "","description": "T#10s"}]},{"comment": "타이머 T2 (TON, 6000ms)","input_branches": [{"elements": [{"element_type": "CONTACT_NO","symbol": "DRAIN_VALVE","address": "","description": ""}]}],"outputs": [{"element_type": "TIMER","symbol": "T2","address": "","description": "T#6s"}]},{"comment": "","input_branches": [{"elements": [{"element_type": "CONTACT_NC","symbol": "DRAIN_VALVE","address": "","description": ""},{"element_type": "CONTACT_NC","symbol": "FILL_VALVE","address": "","description": ""},{"element_type": "CONTACT_NC","symbol": "MIXER","address": "","description": ""},{"element_type": "CONTACT_NO","symbol": "START","address": "","description": ""},{"element_type": "CONTACT_NC","symbol": "STOP","address": "","description": ""},{"element_type": "CONTACT_NC","symbol": "T0.Q","address": "","description": ""}]},{"elements": [{"element_type": "CONTACT_NO","symbol": "FILL_VALVE","address": "","description": ""},{"element_type": "CONTACT_NC","symbol": "STOP","address": "","description": ""},{"element_type": "CONTACT_NC","symbol": "T0.Q","address": "","description": ""}]}],"outputs": [{"element_type": "COIL","symbol": "FILL_VALVE","address": "","description": ""}]},{"comment": "","input_branches": [{"elements": [{"element_type": "CONTACT_NC","symbol": "STOP","address": "","description": ""},{"element_type": "CONTACT_NO","symbol": "T0.Q","address": "","description": ""},{"element_type": "CONTACT_NC","symbol": "T1.Q","address": "","description": ""}]},{"elements": [{"element_type": "CONTACT_NO","symbol": "MIXER","address": "","description": ""},{"element_type": "CONTACT_NC","symbol": "STOP","address": "","description": ""},{"element_type": "CONTACT_NC","symbol": "T1.Q","address": "","description": ""}]}],"outputs": [{"element_type": "COIL","symbol": "MIXER","address": "","description": ""}]},{"comment": "","input_branches": [{"elements": [{"element_type": "CONTACT_NC","symbol": "STOP","address": "","description": ""},{"element_type": "CONTACT_NO","symbol": "T1.Q","address": "","description": ""},{"element_type": "CONTACT_NC","symbol": "T2.Q","address": "","description": ""}]},{"elements": [{"element_type": "CONTACT_NO","symbol": "DRAIN_VALVE","address": "","description": ""},{"element_type": "CONTACT_NC","symbol": "STOP","address": "","description": ""},{"element_type": "CONTACT_NC","symbol": "T2.Q","address": "","description": ""}]}],"outputs": [{"element_type": "COIL","symbol": "DRAIN_VALVE","address": "","description": ""}]}]},"explain": "## 이 장치는 무엇을 하나요\n■ 배치 충전/교반/배출\n입력(사람·센서 신호): START(기동), STOP(정지)\n출력(움직이는 것): FILL_VALVE(1단계), MIXER(2단계), DRAIN_VALVE(3단계)\n타이머 T0: 조건이 유지되면 8초 뒤 신호를 냅니다.\n타이머 T1: 조건이 유지되면 10초 뒤 신호를 냅니다.\n타이머 T2: 조건이 유지되면 6초 뒤 신호를 냅니다.\n\n## 동작 설명 (한 줄씩)\n- 렁 1: FILL_VALVE가 켜져 있음 동안 타이머 T0(T#8s)가 동작합니다.\n- 렁 2: MIXER가 켜져 있음 동안 타이머 T1(T#10s)가 동작합니다.\n- 렁 3: DRAIN_VALVE가 켜져 있음 동안 타이머 T2(T#6s)가 동작합니다.\n- 렁 4: (DRAIN_VALVE가 꺼져 있음, FILL_VALVE가 꺼져 있음, MIXER가 꺼져 있음, START가 켜져 있음, STOP가 꺼져 있음, T0.Q가 꺼져 있음) 또는 (FILL_VALVE가 켜져 있음, STOP가 꺼져 있음, T0.Q가 꺼져 있음) 면 FILL_VALVE가 켜집니다. (자기유지: 한 번 켜지면 정지 조건 전까지 유지)\n- 렁 5: (STOP가 꺼져 있음, T0.Q가 켜져 있음, T1.Q가 꺼져 있음) 또는 (MIXER가 켜져 있음, STOP가 꺼져 있음, T1.Q가 꺼져 있음) 면 MIXER가 켜집니다. (자기유지: 한 번 켜지면 정지 조건 전까지 유지)\n- 렁 6: (STOP가 꺼져 있음, T1.Q가 켜져 있음, T2.Q가 꺼져 있음) 또는 (DRAIN_VALVE가 켜져 있음, STOP가 꺼져 있음, T2.Q가 꺼져 있음) 면 DRAIN_VALVE가 켜집니다. (자기유지: 한 번 켜지면 정지 조건 전까지 유지)\n\n## 안전·검증\n- ✅ 로직 검사 통과 — 이중 코일·인터록 로직·도달성에 문제가 없습니다.\n- ℹ️ 이는 로직 검사이며 기능 안전 인증이 아닙니다. E-stop·가드 등 안전기능은 하드와이어로 구현하세요.","passed": true,"sim": {"inputs": ["START","STOP"],"outputs": ["FILL_VALVE","MIXER","DRAIN_VALVE"],"samples": [{"t": 0,"i": {"START": false,"STOP": false},"o": {"FILL_VALVE": false,"MIXER": false,"DRAIN_VALVE": false}},{"t": 1000,"i": {"START": false,"STOP": false},"o": {"FILL_VALVE": false,"MIXER": false,"DRAIN_VALVE": false}},{"t": 2000,"i": {"START": false,"STOP": false},"o": {"FILL_VALVE": false,"MIXER": false,"DRAIN_VALVE": false}},{"t": 3000,"i": {"START": false,"STOP": false},"o": {"FILL_VALVE": false,"MIXER": false,"DRAIN_VALVE": false}},{"t": 4000,"i": {"START": false,"STOP": false},"o": {"FILL_VALVE": false,"MIXER": false,"DRAIN_VALVE": false}},{"t": 5000,"i": {"START": false,"STOP": false},"o": {"FILL_VALVE": false,"MIXER": false,"DRAIN_VALVE": false}},{"t": 6000,"i": {"START": false,"STOP": false},"o": {"FILL_VALVE": false,"MIXER": false,"DRAIN_VALVE": false}},{"t": 7000,"i": {"START": false,"STOP": false},"o": {"FILL_VALVE": false,"MIXER": false,"DRAIN_VALVE": false}},{"t": 8000,"i": {"START": false,"STOP": false},"o": {"FILL_VALVE": false,"MIXER": false,"DRAIN_VALVE": false}},{"t": 9000,"i": {"START": false,"STOP": false},"o": {"FILL_VALVE": false,"MIXER": false,"DRAIN_VALVE": false}},{"t": 10000,"i": {"START": false,"STOP": false},"o": {"FILL_VALVE": false,"MIXER": false,"DRAIN_VALVE": false}},{"t": 11000,"i": {"START": false,"STOP": false},"o": {"FILL_VALVE": false,"MIXER": false,"DRAIN_VALVE": false}},{"t": 12000,"i": {"START": false,"STOP": false},"o": {"FILL_VALVE": false,"MIXER": false,"DRAIN_VALVE": false}},{"t": 13000,"i": {"START": false,"STOP": false},"o": {"FILL_VALVE": false,"MIXER": false,"DRAIN_VALVE": false}},{"t": 14000,"i": {"START": false,"STOP": false},"o": {"FILL_VALVE": false,"MIXER": false,"DRAIN_VALVE": false}},{"t": 15000,"i": {"START": false,"STOP": false},"o": {"FILL_VALVE": false,"MIXER": false,"DRAIN_VALVE": false}},{"t": 16000,"i": {"START": false,"STOP": false},"o": {"FILL_VALVE": false,"MIXER": false,"DRAIN_VALVE": false}},{"t": 17000,"i": {"START": false,"STOP": false},"o": {"FILL_VALVE": false,"MIXER": false,"DRAIN_VALVE": false}},{"t": 18000,"i": {"START": false,"STOP": false},"o": {"FILL_VALVE": false,"MIXER": false,"DRAIN_VALVE": false}},{"t": 19000,"i": {"START": false,"STOP": false},"o": {"FILL_VALVE": false,"MIXER": false,"DRAIN_VALVE": false}},{"t": 20000,"i": {"START": false,"STOP": false},"o": {"FILL_VALVE": false,"MIXER": false,"DRAIN_VALVE": false}},{"t": 21000,"i": {"START": false,"STOP": false},"o": {"FILL_VALVE": false,"MIXER": false,"DRAIN_VALVE": false}},{"t": 22000,"i": {"START": false,"STOP": false},"o": {"FILL_VALVE": false,"MIXER": false,"DRAIN_VALVE": false}},{"t": 23000,"i": {"START": false,"STOP": false},"o": {"FILL_VALVE": false,"MIXER": false,"DRAIN_VALVE": false}},{"t": 24000,"i": {"START": false,"STOP": false},"o": {"FILL_VALVE": false,"MIXER": false,"DRAIN_VALVE": false}},{"t": 25000,"i": {"START": false,"STOP": false},"o": {"FILL_VALVE": false,"MIXER": false,"DRAIN_VALVE": false}},{"t": 26000,"i": {"START": false,"STOP": false},"o": {"FILL_VALVE": false,"MIXER": false,"DRAIN_VALVE": false}}]}},"duty_standby": {"title": "펌프 리드/래그(듀티-스탠바이)","st": "PUMP_LEAD := ((DEMAND AND NOT SYS_STOP) OR (NOT HIGH_DEMAND) OR PUMP_LEAD) AND NOT ((SYS_STOP) OR (HIGH_DEMAND AND NOT SYS_STOP));\nPUMP_LAG := ((HIGH_DEMAND AND NOT SYS_STOP) OR PUMP_LAG) AND NOT ((NOT HIGH_DEMAND));","ladder": {"title": "펌프 리드/래그(듀티-스탠바이)","rungs": [{"comment": "","input_branches": [{"elements": [{"element_type": "CONTACT_NO","symbol": "DEMAND","address": "","description": ""},{"element_type": "CONTACT_NC","symbol": "HIGH_DEMAND","address": "","description": ""},{"element_type": "CONTACT_NC","symbol": "SYS_STOP","address": "","description": ""}]},{"elements": [{"element_type": "CONTACT_NC","symbol": "HIGH_DEMAND","address": "","description": ""},{"element_type": "CONTACT_NC","symbol": "SYS_STOP","address": "","description": ""}]},{"elements": [{"element_type": "CONTACT_NC","symbol": "HIGH_DEMAND","address": "","description": ""},{"element_type": "CONTACT_NO","symbol": "PUMP_LEAD","address": "","description": ""},{"element_type": "CONTACT_NC","symbol": "SYS_STOP","address": "","description": ""}]}],"outputs": [{"element_type": "COIL","symbol": "PUMP_LEAD","address": "","description": ""}]},{"comment": "","input_branches": [{"elements": [{"element_type": "CONTACT_NO","symbol": "HIGH_DEMAND","address": "","description": ""},{"element_type": "CONTACT_NC","symbol": "SYS_STOP","address": "","description": ""}]},{"elements": [{"element_type": "CONTACT_NO","symbol": "HIGH_DEMAND","address": "","description": ""},{"element_type": "CONTACT_NO","symbol": "PUMP_LAG","address": "","description": ""}]}],"outputs": [{"element_type": "COIL","symbol": "PUMP_LAG","address": "","description": ""}]}]},"explain": "## 이 장치는 무엇을 하나요\n■ 펌프 리드/래그(듀티-스탠바이)\n입력(사람·센서 신호): DEMAND(수요), HIGH_DEMAND(고수요), SYS_STOP(정지)\n출력(움직이는 것): PUMP_LEAD(리드 펌프), PUMP_LAG(래그 펌프)\n\n## 동작 설명 (한 줄씩)\n- 렁 1: (DEMAND가 켜져 있음, HIGH_DEMAND가 꺼져 있음, SYS_STOP가 꺼져 있음) 또는 (HIGH_DEMAND가 꺼져 있음, SYS_STOP가 꺼져 있음) 또는 (HIGH_DEMAND가 꺼져 있음, PUMP_LEAD가 켜져 있음, SYS_STOP가 꺼져 있음) 면 PUMP_LEAD가 켜집니다. (자기유지: 한 번 켜지면 정지 조건 전까지 유지)\n- 렁 2: (HIGH_DEMAND가 켜져 있음, SYS_STOP가 꺼져 있음) 또는 (HIGH_DEMAND가 켜져 있음, PUMP_LAG가 켜져 있음) 면 PUMP_LAG가 켜집니다. (자기유지: 한 번 켜지면 정지 조건 전까지 유지)\n\n## 안전·검증\n- ✅ 로직 검사 통과 — 이중 코일·인터록 로직·도달성에 문제가 없습니다.\n- ℹ️ 이는 로직 검사이며 기능 안전 인증이 아닙니다. E-stop·가드 등 안전기능은 하드와이어로 구현하세요.","passed": true,"sim": {"inputs": ["DEMAND","HIGH_DEMAND","SYS_STOP"],"outputs": ["PUMP_LEAD","PUMP_LAG"],"samples": [{"t": 0,"i": {"DEMAND": false,"HIGH_DEMAND": false,"SYS_STOP": false},"o": {"PUMP_LEAD": true,"PUMP_LAG": false}},{"t": 200,"i": {"DEMAND": true,"HIGH_DEMAND": false,"SYS_STOP": false},"o": {"PUMP_LEAD": true,"PUMP_LAG": false}},{"t": 400,"i": {"DEMAND": true,"HIGH_DEMAND": false,"SYS_STOP": false},"o": {"PUMP_LEAD": true,"PUMP_LAG": false}},{"t": 600,"i": {"DEMAND": true,"HIGH_DEMAND": false,"SYS_STOP": false},"o": {"PUMP_LEAD": true,"PUMP_LAG": false}},{"t": 800,"i": {"DEMAND": true,"HIGH_DEMAND": false,"SYS_STOP": false},"o": {"PUMP_LEAD": true,"PUMP_LAG": false}},{"t": 1000,"i": {"DEMAND": true,"HIGH_DEMAND": false,"SYS_STOP": false},"o": {"PUMP_LEAD": true,"PUMP_LAG": false}},{"t": 1200,"i": {"DEMAND": true,"HIGH_DEMAND": false,"SYS_STOP": false},"o": {"PUMP_LEAD": true,"PUMP_LAG": false}},{"t": 1400,"i": {"DEMAND": true,"HIGH_DEMAND": false,"SYS_STOP": false},"o": {"PUMP_LEAD": true,"PUMP_LAG": false}},{"t": 1600,"i": {"DEMAND": true,"HIGH_DEMAND": false,"SYS_STOP": false},"o": {"PUMP_LEAD": true,"PUMP_LAG": false}},{"t": 1800,"i": {"DEMAND": true,"HIGH_DEMAND": false,"SYS_STOP": false},"o": {"PUMP_LEAD": true,"PUMP_LAG": false}},{"t": 2000,"i": {"DEMAND": true,"HIGH_DEMAND": true,"SYS_STOP": false},"o": {"PUMP_LEAD": false,"PUMP_LAG": true}},{"t": 2200,"i": {"DEMAND": true,"HIGH_DEMAND": true,"SYS_STOP": false},"o": {"PUMP_LEAD": false,"PUMP_LAG": true}},{"t": 2400,"i": {"DEMAND": true,"HIGH_DEMAND": true,"SYS_STOP": false},"o": {"PUMP_LEAD": false,"PUMP_LAG": true}},{"t": 2600,"i": {"DEMAND": true,"HIGH_DEMAND": true,"SYS_STOP": false},"o": {"PUMP_LEAD": false,"PUMP_LAG": true}},{"t": 2800,"i": {"DEMAND": true,"HIGH_DEMAND": true,"SYS_STOP": false},"o": {"PUMP_LEAD": false,"PUMP_LAG": true}},{"t": 3000,"i": {"DEMAND": true,"HIGH_DEMAND": true,"SYS_STOP": false},"o": {"PUMP_LEAD": false,"PUMP_LAG": true}},{"t": 3200,"i": {"DEMAND": true,"HIGH_DEMAND": true,"SYS_STOP": false},"o": {"PUMP_LEAD": false,"PUMP_LAG": true}},{"t": 3400,"i": {"DEMAND": true,"HIGH_DEMAND": true,"SYS_STOP": false},"o": {"PUMP_LEAD": false,"PUMP_LAG": true}},{"t": 3600,"i": {"DEMAND": true,"HIGH_DEMAND": true,"SYS_STOP": false},"o": {"PUMP_LEAD": false,"PUMP_LAG": true}},{"t": 3800,"i": {"DEMAND": true,"HIGH_DEMAND": true,"SYS_STOP": false},"o": {"PUMP_LEAD": false,"PUMP_LAG": true}},{"t": 4000,"i": {"DEMAND": true,"HIGH_DEMAND": false,"SYS_STOP": false},"o": {"PUMP_LEAD": true,"PUMP_LAG": false}},{"t": 4200,"i": {"DEMAND": true,"HIGH_DEMAND": false,"SYS_STOP": false},"o": {"PUMP_LEAD": true,"PUMP_LAG": false}},{"t": 4400,"i": {"DEMAND": true,"HIGH_DEMAND": false,"SYS_STOP": false},"o": {"PUMP_LEAD": true,"PUMP_LAG": false}},{"t": 4600,"i": {"DEMAND": true,"HIGH_DEMAND": false,"SYS_STOP": false},"o": {"PUMP_LEAD": true,"PUMP_LAG": false}},{"t": 4800,"i": {"DEMAND": true,"HIGH_DEMAND": false,"SYS_STOP": false},"o": {"PUMP_LEAD": true,"PUMP_LAG": false}},{"t": 5000,"i": {"DEMAND": true,"HIGH_DEMAND": false,"SYS_STOP": true},"o": {"PUMP_LEAD": false,"PUMP_LAG": false}},{"t": 5200,"i": {"DEMAND": true,"HIGH_DEMAND": false,"SYS_STOP": true},"o": {"PUMP_LEAD": false,"PUMP_LAG": false}},{"t": 5400,"i": {"DEMAND": true,"HIGH_DEMAND": false,"SYS_STOP": false},"o": {"PUMP_LEAD": true,"PUMP_LAG": false}},{"t": 5600,"i": {"DEMAND": true,"HIGH_DEMAND": false,"SYS_STOP": false},"o": {"PUMP_LEAD": true,"PUMP_LAG": false}},{"t": 5800,"i": {"DEMAND": true,"HIGH_DEMAND": false,"SYS_STOP": false},"o": {"PUMP_LEAD": true,"PUMP_LAG": false}},{"t": 6000,"i": {"DEMAND": true,"HIGH_DEMAND": false,"SYS_STOP": false},"o": {"PUMP_LEAD": true,"PUMP_LAG": false}}]}},"cascade_conveyor": {"title": "다단 컨베이어 순차 기동·정지(하류기동/상류정지)","st": "// 타이머 T0 (TON, 3000ms)\nT0(IN := CONV_DOWN, PT := T#3s);\n// 타이머 T1 (TON, 3000ms)\nT1(IN := CONV_MID, PT := T#3s);\n// 타이머 T2 (TON, 3000ms)\nT2(IN := STOP_PB AND CONV_UP, PT := T#3s);\n// 타이머 T3 (TON, 3000ms)\nT3(IN := STOP_PB AND CONV_MID, PT := T#3s);\n\nCONV_DOWN := ((START_PB AND NOT STOP_PB) OR (T0.Q AND NOT STOP_PB) OR (T1.Q AND NOT STOP_PB) OR (STOP_PB) OR (STOP_PB) OR (T2.Q) OR CONV_DOWN) AND NOT ((STOP_PB) OR (T3.Q));\nCONV_MID := ((T0.Q AND NOT STOP_PB) OR (T1.Q AND NOT STOP_PB) OR (STOP_PB) OR CONV_MID) AND NOT ((STOP_PB) OR (T2.Q));\nCONV_UP := ((T1.Q AND NOT STOP_PB) OR CONV_UP) AND NOT ((STOP_PB));","ladder": {"title": "다단 컨베이어 순차 기동·정지(하류기동/상류정지)","rungs": [{"comment": "타이머 T0 (TON, 3000ms)","input_branches": [{"elements": [{"element_type": "CONTACT_NO","symbol": "CONV_DOWN","address": "","description": ""}]}],"outputs": [{"element_type": "TIMER","symbol": "T0","address": "","description": "T#3s"}]},{"comment": "타이머 T1 (TON, 3000ms)","input_branches": [{"elements": [{"element_type": "CONTACT_NO","symbol": "CONV_MID","address": "","description": ""}]}],"outputs": [{"element_type": "TIMER","symbol": "T1","address": "","description": "T#3s"}]},{"comment": "타이머 T2 (TON, 3000ms)","input_branches": [{"elements": [{"element_type": "CONTACT_NO","symbol": "CONV_UP","address": "","description": ""},{"element_type": "CONTACT_NO","symbol": "STOP_PB","address": "","description": ""}]}],"outputs": [{"element_type": "TIMER","symbol": "T2","address": "","description": "T#3s"}]},{"comment": "타이머 T3 (TON, 3000ms)","input_branches": [{"elements": [{"element_type": "CONTACT_NO","symbol": "CONV_MID","address": "","description": ""},{"element_type": "CONTACT_NO","symbol": "STOP_PB","address": "","description": ""}]}],"outputs": [{"element_type": "TIMER","symbol": "T3","address": "","description": "T#3s"}]},{"comment": "","input_branches": [{"elements": [{"element_type": "CONTACT_NO","symbol": "START_PB","address": "","description": ""},{"element_type": "CONTACT_NC","symbol": "STOP_PB","address": "","description": ""},{"element_type": "CONTACT_NC","symbol": "T3.Q","address": "","description": ""}]},{"elements": [{"element_type": "CONTACT_NC","symbol": "STOP_PB","address": "","description": ""},{"element_type": "CONTACT_NO","symbol": "T0.Q","address": "","description": ""},{"element_type": "CONTACT_NC","symbol": "T3.Q","address": "","description": ""}]},{"elements": [{"element_type": "CONTACT_NC","symbol": "STOP_PB","address": "","description": ""},{"element_type": "CONTACT_NO","symbol": "T1.Q","address": "","description": ""},{"element_type": "CONTACT_NC","symbol": "T3.Q","address": "","description": ""}]},{"elements": [{"element_type": "CONTACT_NC","symbol": "STOP_PB","address": "","description": ""},{"element_type": "CONTACT_NO","symbol": "T2.Q","address": "","description": ""},{"element_type": "CONTACT_NC","symbol": "T3.Q","address": "","description": ""}]},{"elements": [{"element_type": "CONTACT_NO","symbol": "CONV_DOWN","address": "","description": ""},{"element_type": "CONTACT_NC","symbol": "STOP_PB","address": "","description": ""},{"element_type": "CONTACT_NC","symbol": "T3.Q","address": "","description": ""}]}],"outputs": [{"element_type": "COIL","symbol": "CONV_DOWN","address": "","description": ""}]},{"comment": "","input_branches": [{"elements": [{"element_type": "CONTACT_NC","symbol": "STOP_PB","address": "","description": ""},{"element_type": "CONTACT_NO","symbol": "T0.Q","address": "","description": ""},{"element_type": "CONTACT_NC","symbol": "T2.Q","address": "","description": ""}]},{"elements": [{"element_type": "CONTACT_NC","symbol": "STOP_PB","address": "","description": ""},{"element_type": "CONTACT_NO","symbol": "T1.Q","address": "","description": ""},{"element_type": "CONTACT_NC","symbol": "T2.Q","address": "","description": ""}]},{"elements": [{"element_type": "CONTACT_NO","symbol": "CONV_MID","address": "","description": ""},{"element_type": "CONTACT_NC","symbol": "STOP_PB","address": "","description": ""},{"element_type": "CONTACT_NC","symbol": "T2.Q","address": "","description": ""}]}],"outputs": [{"element_type": "COIL","symbol": "CONV_MID","address": "","description": ""}]},{"comment": "","input_branches": [{"elements": [{"element_type": "CONTACT_NC","symbol": "STOP_PB","address": "","description": ""},{"element_type": "CONTACT_NO","symbol": "T1.Q","address": "","description": ""}]},{"elements": [{"element_type": "CONTACT_NO","symbol": "CONV_UP","address": "","description": ""},{"element_type": "CONTACT_NC","symbol": "STOP_PB","address": "","description": ""}]}],"outputs": [{"element_type": "COIL","symbol": "CONV_UP","address": "","description": ""}]}]},"explain": "## 이 장치는 무엇을 하나요\n■ 다단 컨베이어 순차 기동·정지(하류기동/상류정지)\n입력(사람·센서 신호): START_PB(기동), STOP_PB(정지)\n출력(움직이는 것): CONV_DOWN(하류 컨베이어), CONV_MID(중간 컨베이어), CONV_UP(상류 컨베이어)\n타이머 T0: 조건이 유지되면 3초 뒤 신호를 냅니다.\n타이머 T1: 조건이 유지되면 3초 뒤 신호를 냅니다.\n타이머 T2: 조건이 유지되면 3초 뒤 신호를 냅니다.\n타이머 T3: 조건이 유지되면 3초 뒤 신호를 냅니다.\n\n## 동작 설명 (한 줄씩)\n- 렁 1: CONV_DOWN가 켜져 있음 동안 타이머 T0(T#3s)가 동작합니다.\n- 렁 2: CONV_MID가 켜져 있음 동안 타이머 T1(T#3s)가 동작합니다.\n- 렁 3: CONV_UP가 켜져 있음, STOP_PB가 켜져 있음 동안 타이머 T2(T#3s)가 동작합니다.\n- 렁 4: CONV_MID가 켜져 있음, STOP_PB가 켜져 있음 동안 타이머 T3(T#3s)가 동작합니다.\n- 렁 5: (START_PB가 켜져 있음, STOP_PB가 꺼져 있음, T3.Q가 꺼져 있음) 또는 (STOP_PB가 꺼져 있음, T0.Q가 켜져 있음, T3.Q가 꺼져 있음) 또는 (STOP_PB가 꺼져 있음, T1.Q가 켜져 있음, T3.Q가 꺼져 있음) 또는 (STOP_PB가 꺼져 있음, T2.Q가 켜져 있음, T3.Q가 꺼져 있음) 또는 (CONV_DOWN가 켜져 있음, STOP_PB가 꺼져 있음, T3.Q가 꺼져 있음) 면 CONV_DOWN가 켜집니다. (자기유지: 한 번 켜지면 정지 조건 전까지 유지)\n- 렁 6: (STOP_PB가 꺼져 있음, T0.Q가 켜져 있음, T2.Q가 꺼져 있음) 또는 (STOP_PB가 꺼져 있음, T1.Q가 켜져 있음, T2.Q가 꺼져 있음) 또는 (CONV_MID가 켜져 있음, STOP_PB가 꺼져 있음, T2.Q가 꺼져 있음) 면 CONV_MID가 켜집니다. (자기유지: 한 번 켜지면 정지 조건 전까지 유지)\n- 렁 7: (STOP_PB가 꺼져 있음, T1.Q가 켜져 있음) 또는 (CONV_UP가 켜져 있음, STOP_PB가 꺼져 있음) 면 CONV_UP가 켜집니다. (자기유지: 한 번 켜지면 정지 조건 전까지 유지)\n\n## 안전·검증\n- ✅ 로직 검사 통과 — 이중 코일·인터록 로직·도달성에 문제가 없습니다.\n- ℹ️ 이는 로직 검사이며 기능 안전 인증이 아닙니다. E-stop·가드 등 안전기능은 하드와이어로 구현하세요.","passed": true,"sim": {"inputs": ["START_PB","STOP_PB"],"outputs": ["CONV_DOWN","CONV_MID","CONV_UP"],"samples": [{"t": 0,"i": {"START_PB": false,"STOP_PB": false},"o": {"CONV_DOWN": false,"CONV_MID": false,"CONV_UP": false}},{"t": 500,"i": {"START_PB": true,"STOP_PB": false},"o": {"CONV_DOWN": true,"CONV_MID": false,"CONV_UP": false}},{"t": 1000,"i": {"START_PB": false,"STOP_PB": false},"o": {"CONV_DOWN": true,"CONV_MID": false,"CONV_UP": false}},{"t": 1500,"i": {"START_PB": false,"STOP_PB": false},"o": {"CONV_DOWN": true,"CONV_MID": false,"CONV_UP": false}},{"t": 2000,"i": {"START_PB": false,"STOP_PB": false},"o": {"CONV_DOWN": true,"CONV_MID": false,"CONV_UP": false}},{"t": 2500,"i": {"START_PB": false,"STOP_PB": false},"o": {"CONV_DOWN": true,"CONV_MID": false,"CONV_UP": false}},{"t": 3000,"i": {"START_PB": false,"STOP_PB": false},"o": {"CONV_DOWN": true,"CONV_MID": false,"CONV_UP": false}},{"t": 3500,"i": {"START_PB": false,"STOP_PB": false},"o": {"CONV_DOWN": true,"CONV_MID": false,"CONV_UP": false}},{"t": 4000,"i": {"START_PB": false,"STOP_PB": false},"o": {"CONV_DOWN": true,"CONV_MID": true,"CONV_UP": false}},{"t": 4500,"i": {"START_PB": false,"STOP_PB": false},"o": {"CONV_DOWN": true,"CONV_MID": true,"CONV_UP": false}},{"t": 5000,"i": {"START_PB": false,"STOP_PB": false},"o": {"CONV_DOWN": true,"CONV_MID": true,"CONV_UP": false}},{"t": 5500,"i": {"START_PB": false,"STOP_PB": false},"o": {"CONV_DOWN": true,"CONV_MID": true,"CONV_UP": false}},{"t": 6000,"i": {"START_PB": false,"STOP_PB": false},"o": {"CONV_DOWN": true,"CONV_MID": true,"CONV_UP": false}},{"t": 6500,"i": {"START_PB": false,"STOP_PB": false},"o": {"CONV_DOWN": true,"CONV_MID": true,"CONV_UP": false}},{"t": 7000,"i": {"START_PB": false,"STOP_PB": false},"o": {"CONV_DOWN": true,"CONV_MID": true,"CONV_UP": false}},{"t": 7500,"i": {"START_PB": false,"STOP_PB": false},"o": {"CONV_DOWN": true,"CONV_MID": true,"CONV_UP": true}},{"t": 8000,"i": {"START_PB": false,"STOP_PB": false},"o": {"CONV_DOWN": true,"CONV_MID": true,"CONV_UP": true}},{"t": 8500,"i": {"START_PB": false,"STOP_PB": false},"o": {"CONV_DOWN": true,"CONV_MID": true,"CONV_UP": true}},{"t": 9000,"i": {"START_PB": false,"STOP_PB": false},"o": {"CONV_DOWN": true,"CONV_MID": true,"CONV_UP": true}},{"t": 9500,"i": {"START_PB": false,"STOP_PB": false},"o": {"CONV_DOWN": true,"CONV_MID": true,"CONV_UP": true}},{"t": 10000,"i": {"START_PB": false,"STOP_PB": false},"o": {"CONV_DOWN": true,"CONV_MID": true,"CONV_UP": true}},{"t": 10500,"i": {"START_PB": false,"STOP_PB": false},"o": {"CONV_DOWN": true,"CONV_MID": true,"CONV_UP": true}},{"t": 11000,"i": {"START_PB": false,"STOP_PB": true},"o": {"CONV_DOWN": false,"CONV_MID": false,"CONV_UP": false}},{"t": 11500,"i": {"START_PB": false,"STOP_PB": true},"o": {"CONV_DOWN": false,"CONV_MID": false,"CONV_UP": false}},{"t": 12000,"i": {"START_PB": false,"STOP_PB": false},"o": {"CONV_DOWN": false,"CONV_MID": false,"CONV_UP": false}},{"t": 12500,"i": {"START_PB": false,"STOP_PB": false},"o": {"CONV_DOWN": false,"CONV_MID": false,"CONV_UP": false}},{"t": 13000,"i": {"START_PB": false,"STOP_PB": false},"o": {"CONV_DOWN": false,"CONV_MID": false,"CONV_UP": false}},{"t": 13500,"i": {"START_PB": false,"STOP_PB": false},"o": {"CONV_DOWN": false,"CONV_MID": false,"CONV_UP": false}},{"t": 14000,"i": {"START_PB": false,"STOP_PB": false},"o": {"CONV_DOWN": false,"CONV_MID": false,"CONV_UP": false}}]}}};
const ids = Object.keys(DEMO);

function tg(sim){
  const cw=10;
  const row=(s,blue)=>`<tr><td class="lbl" style="color:${blue?'#58a6ff':'#3fb950'}">${s}</td>`+
    sim.samples.map(x=>`<td style="width:${cw}px;height:15px;padding:0;background:${(blue?x.i:x.o)[s]?(blue?'#58a6ff':'#3fb950'):'#0c121b'};border:1px solid #070b11"></td>`).join("")+`</tr>`;
  return `<table class="tg">`+sim.inputs.map(s=>row(s,true)).join("")+sim.outputs.map(s=>row(s,false)).join("")+`</table>`;
}

/* ============================================================
   메타 — 엔진 DeviceAllocator(LS XGK) 동일 규칙 주소 + 기기 태그
   실측 비율 기준: 1 유닛 = 1 m (컨베이어 작업높이 0.75m·벨트폭 0.6m,
   광전센서 30~50mm, 로봇셀 3×4m + 안전펜스 1.4m — ISO 13857)
   ============================================================ */
const META={
 motor_start_stop:{
  scene:"conveyor",
  addr:{START:"P0000",STOP:"P0001",MOTOR:"P0002"},
  desc:{START:"기동 버튼",STOP:"정지 버튼",MOTOR:"컨베이어 모터"},
  buttons:[{sym:"START",label:"기동",c:"#1f9d4d"},{sym:"STOP",label:"정지",c:"#c93c3c"}],
  tags:{MOTOR:{tag:"M-101",name:"벨트컨베이어 모터",rated:3.6}},
  faults:[{id:"tripM",label:"M-101 과부하 트립",sym:"MOTOR",type:"trip"}],
  verify:["이중 코일 0건 — MOTOR 코일 단일 대입","자기유지 회로 도달성 검사 통과",
          "STOP 지배성 — 정지 입력 시 모든 통전 경로 차단","OpenPLC 런타임 차분검증 bit-for-bit 일치"]},
 fwd_rev:{
  scene:"shuttle",
  addr:{FWD_PB:"P0000",REV_PB:"P0001",STOP:"P0002",MOTOR_FWD:"P0003",MOTOR_REV:"P0004"},
  desc:{FWD_PB:"정방향 버튼",REV_PB:"역방향 버튼",STOP:"정지 버튼",MOTOR_FWD:"정방향 구동",MOTOR_REV:"역방향 구동"},
  buttons:[{sym:"FWD_PB",label:"정방향",c:"#2563b8"},{sym:"REV_PB",label:"역방향",c:"#6d4fd6"},{sym:"STOP",label:"정지",c:"#c93c3c"}],
  tags:{MOTOR_FWD:{tag:"M-201",name:"이송대차 정방향",rated:5.2},MOTOR_REV:{tag:"M-202",name:"이송대차 역방향",rated:5.2}},
  verify:["Z3 SMT 증명 — MOTOR_FWD ∧ MOTOR_REV = UNSAT (동시 출력 수학적 불가능)",
          "상호 인터록 — 반대측 코일·버튼 NC 접점 직렬","이중 코일 0건 · STOP 지배성 확인",
          "OpenPLC 런타임 차분검증 bit-for-bit 일치"]},
 car_wash:{
  scene:"carwash",
  addr:{START:"P0000",STOP:"P0001",SOAP:"P0002",RINSE:"P0003",DRY:"P0004",T0:"T0000",T1:"T0001",T2:"T0002"},
  desc:{START:"시작 버튼",STOP:"정지 버튼",SOAP:"비누 분사",RINSE:"헹굼 노즐",DRY:"건조 팬",
        T0:"비누 단계 타이머",T1:"헹굼 단계 타이머",T2:"건조 단계 타이머"},
  buttons:[{sym:"START",label:"시작",c:"#1f9d4d"},{sym:"STOP",label:"정지",c:"#c93c3c"}],
  tags:{SOAP:{tag:"V-301",name:"비누 분사 밸브",rated:0.8},RINSE:{tag:"P-301",name:"헹굼 펌프",rated:2.4},DRY:{tag:"FN-301",name:"건조 블로워",rated:7.5}},
  verify:["단계 배타 진행 — 비누→헹굼→건조 순서만 도달 가능","IEC 표준 TON 3개 — R := 리셋(실런타임 호환)",
          "이중 코일 0건 · STOP 시 전 단계 즉시 차단","OpenPLC 런타임 차분검증 bit-for-bit 일치"]},
 count_eject:{
  scene:"counter",
  addr:{PART_SENSOR:"P0000",RESET_PB:"P0001",EJECT:"P0002",C1:"C0000"},
  desc:{PART_SENSOR:"광전센서(부품 검출)",RESET_PB:"리셋 버튼",EJECT:"배출 실린더",C1:"부품 카운터 CTU"},
  buttons:[{sym:"RESET_PB",label:"리셋",c:"#b8860b"}],
  autoInputs:{PART_SENSOR:"센서 · 자동"},
  tags:{EJECT:{tag:"CY-101",name:"배출 에어실린더",rated:1.1}},
  faults:[{id:"stuckS",label:"SN-101 센서 고착(ON)",sym:"PART_SENSOR",type:"stuck_on"}],
  verify:["CTU 카운터 — IEC 표준 'R :=' 리셋 (실런타임 로드 확인)","EJECT 래치 도달성·리셋 경로 검사 통과",
          "이중 코일 0건","OpenPLC 런타임 차분검증 bit-for-bit 일치"]},
 conveyor_divert:{
  scene:"vision",
  addr:{SEL_A:"P0000",SEL_B:"P0001",DIV_STOP:"P0002",GATE_A:"P0003",GATE_B:"P0004"},
  desc:{SEL_A:"게이트 A 선택(비전 OK)",SEL_B:"게이트 B 선택(비전 NG)",DIV_STOP:"분기 정지",GATE_A:"양품 게이트",GATE_B:"불량 게이트"},
  buttons:[{sym:"SEL_A",label:"게이트 A",c:"#2563b8"},{sym:"SEL_B",label:"게이트 B",c:"#6d4fd6"},{sym:"DIV_STOP",label:"분기 정지",c:"#c93c3c"}],
  autoInputs:{SEL_A:"비전 판정 · 자동",SEL_B:"비전 판정 · 자동"},
  tags:{GATE_A:{tag:"DV-701A",name:"양품 게이트",rated:0.7},GATE_B:{tag:"DV-701B",name:"불량 분기 게이트",rated:0.7}},
  faults:[{id:"camOff",label:"VS-701 카메라 정지",type:"custom"}],
  verify:["게이트 상호 인터록 — GATE_A ∧ GATE_B 동시 ON 불가(NC 교차)",
          "DIV_STOP 지배성 — 정지 시 양 게이트 즉시 차단",
          "래치 도달성 — SEL 펄스로 전환·유지 검사 통과",
          "OpenPLC 런타임 차분검증 — bit-for-bit 일치"]},
 weld_cell:{
  scene:"weld",
  addr:{WELD_START:"P0000",WELD_STOP:"P0001",CLAMP:"P0002",WELD:"P0003",UNCLAMP:"P0004",T0:"T0000",T1:"T0001",T2:"T0002"},
  desc:{WELD_START:"사이클 시작",WELD_STOP:"사이클 정지",CLAMP:"클램프 닫힘",WELD:"용접 아크",UNCLAMP:"클램프 해제",
        T0:"클램프 단계(3s)",T1:"용접 단계(5s)",T2:"해제 단계(3s)"},
  buttons:[{sym:"WELD_START",label:"사이클",c:"#1f9d4d"},{sym:"WELD_STOP",label:"정지",c:"#c93c3c"}],
  tags:{CLAMP:{tag:"CL-401",name:"공압 클램프",rated:0.9},WELD:{tag:"RB-401",name:"용접로봇 토치",rated:14.2},UNCLAMP:{tag:"CL-402",name:"클램프 해제",rated:0.9}},
  verify:["단계 배타 — 클램프/용접/해제 동시 ON 불가(상태 전이 검사)","WELD_STOP 지배성 — 어느 단계든 즉시 차단",
          "이중 코일 0건 · TON 3단 시퀀스 도달성","OpenPLC 런타임 차분검증 bit-for-bit 일치"]},
 batch_fill_mix_drain:{
  scene:"batch",
  addr:{START:"P0000",STOP:"P0001",FILL_VALVE:"P0002",MIXER:"P0003",DRAIN_VALVE:"P0004",T0:"T0000",T1:"T0001",T2:"T0002"},
  desc:{START:"배치 시작",STOP:"배치 정지",FILL_VALVE:"충전 밸브",MIXER:"교반기",DRAIN_VALVE:"배출 밸브",
        T0:"충전 단계(8s)",T1:"교반 단계(10s)",T2:"배출 단계(6s)"},
  buttons:[{sym:"START",label:"배치 시작",c:"#1f9d4d"},{sym:"STOP",label:"정지",c:"#c93c3c"}],
  tags:{FILL_VALVE:{tag:"V-501",name:"충전 솔레노이드",rated:0.6},MIXER:{tag:"AG-501",name:"교반 모터",rated:11.0},DRAIN_VALVE:{tag:"V-502",name:"배출 솔레노이드",rated:0.6}},
  analog:{D0000:{name:"배치 탱크 레벨",unit:"%",get:(st,L)=>Math.round(st.level*100)},
          D0001:{name:"제품 드럼 충전",unit:"%",get:(st,L)=>Math.round(st.drum*100)}},
  verify:["충전→교반→배출 순서만 도달 가능(상태 전이 검사)","TON 8s/10s/6s — IEC 표준, 프리셋 보존",
          "이중 코일 0건 · STOP 시 전 밸브 차단","OpenPLC 런타임 차분검증 bit-for-bit 일치"]},
 duty_standby:{
  scene:"pumps",
  addr:{DEMAND:"P0000",HIGH_DEMAND:"P0001",SYS_STOP:"P0002",PUMP_LEAD:"P0003",PUMP_LAG:"P0004"},
  desc:{DEMAND:"수요 수위 센서(저)",HIGH_DEMAND:"수요 수위 센서(고)",SYS_STOP:"계통 정지",PUMP_LEAD:"리드 펌프 A",PUMP_LAG:"래그 펌프 B"},
  buttons:[{sym:"SYS_STOP",label:"계통 정지",c:"#c93c3c"}],
  autoInputs:{DEMAND:"수위 센서 · 자동",HIGH_DEMAND:"수위 센서 · 자동"},
  tags:{PUMP_LEAD:{tag:"P-801A",name:"리드 펌프 15kW",rated:28},PUMP_LAG:{tag:"P-801B",name:"래그 펌프 15kW",rated:28}},
  faults:[{id:"tripLead",label:"P-801A 트립",sym:"PUMP_LEAD",type:"trip"}],
  analog:{D0000:{name:"탱크 수위",unit:"%",get:(st,L)=>Math.round(st.level*100)},
          D0001:{name:"공급 유량",unit:"㎥/h",get:(st,L)=>(effL(L,"PUMP_LEAD")?30:0)+(effL(L,"PUMP_LAG")?30:0)}},
  verify:["리드/래그 전환 도달성 — 수요 단계별 상태 검사 통과",
          "SYS_STOP 지배성 — 양 펌프 즉시 차단",
          "이중 코일 0건 · 래치 회로 검증",
          "OpenPLC 런타임 차분검증 — bit-for-bit 일치"]},
 cascade_conveyor:{
  scene:"cascade",
  addr:{START_PB:"P0000",STOP_PB:"P0001",CONV_DOWN:"P0002",CONV_MID:"P0003",CONV_UP:"P0004",T0:"T0000",T1:"T0001",T2:"T0002",T3:"T0003"},
  desc:{START_PB:"라인 기동",STOP_PB:"라인 정지",CONV_DOWN:"하류 컨베이어",CONV_MID:"중간 컨베이어",CONV_UP:"상류 컨베이어",
        T0:"하류→중간 지연(3s)",T1:"중간→상류 지연(3s)",T2:"정지 시퀀스 T2",T3:"정지 시퀀스 T3"},
  buttons:[{sym:"START_PB",label:"라인 기동",c:"#1f9d4d"},{sym:"STOP_PB",label:"라인 정지",c:"#c93c3c"}],
  tags:{CONV_DOWN:{tag:"CV-603",name:"하류 벨트",rated:3.6},CONV_MID:{tag:"CV-602",name:"중간 벨트",rated:3.6},CONV_UP:{tag:"CV-601",name:"상류 벨트",rated:3.6}},
  faults:[{id:"tripMid",label:"CV-602 모터 트립",sym:"CONV_MID",type:"trip"}],
  verify:["하류 우선 기동 — 3초 간격 순차(자재 적체 방지)","STOP 지배성 — 전 벨트 정지 보장",
          "이중 코일 0건 · TON 4개 도달성","OpenPLC 런타임 차분검증 bit-for-bit 일치"]}
};

/* PLC 기종 카탈로그 — app/catalog.py 동일 데이터(공개 사양 요약·납품 전 데이터시트 확인) */
const PLC_CATALOG=[
 {v:"LS",model:"XGK-CPUE",dio:1536,sk:32,us:0.084,cap:"32K 스텝",tm:2048,cn:2048,comm:"RS-232C·USB",prof:"LS XGK(P/T/C 10진)"},
 {v:"LS",model:"XGK-CPUH",dio:6144,sk:64,us:0.028,cap:"64K 스텝",tm:2048,cn:2048,comm:"RS-232C·USB·Ethernet",prof:"LS XGK(P/T/C 10진)"},
 {v:"LS",model:"XBC-DR32H",dio:384,sk:15,us:0.094,cap:"15K 스텝",tm:256,cn:256,comm:"RS-232C·RS-485",prof:"LS XGK(P/T/C 10진)"},
 {v:"LS",model:"XGI-CPUU",dio:6144,sk:null,us:0.028,cap:"1MB(IEC)",tm:2048,cn:2048,comm:"USB·Ethernet",prof:"LS XGI(%IX/%QX)"},
 {v:"MITSUBISHI",model:"FX5U-32MR/ES",dio:512,sk:64,us:0.034,cap:"64K 스텝",tm:1024,cn:1024,comm:"RS-485·Ethernet",prof:"MELSEC(X/Y 8진)"},
 {v:"MITSUBISHI",model:"Q03UDECPU",dio:4096,sk:30,us:0.02,cap:"30K 스텝",tm:2048,cn:1024,comm:"USB·Ethernet",prof:"MELSEC(X/Y 16진)"},
 {v:"MITSUBISHI",model:"R04CPU",dio:4096,sk:40,us:0.0098,cap:"40K 스텝",tm:2048,cn:1024,comm:"USB·Ethernet",prof:"MELSEC iQ-R"},
 {v:"SIEMENS",model:"CPU 1212C",dio:282,sk:null,us:0.08,cap:"100KB",tm:null,cn:null,comm:"PROFINET",prof:"S7(%I/%Q)"},
 {v:"SIEMENS",model:"CPU 1214C",dio:284,sk:null,us:0.08,cap:"125KB",tm:null,cn:null,comm:"PROFINET",prof:"S7(%I/%Q)"},
 {v:"SIEMENS",model:"CPU 1515-2 PN",dio:8192,sk:null,us:0.01,cap:"500KB+3MB",tm:null,cn:null,comm:"PROFINET×2",prof:"S7(%I/%Q)"},
 {v:"OMRON",model:"CP1L-EM30",dio:150,sk:10,us:0.55,cap:"10K 스텝",tm:256,cn:256,comm:"USB·Ethernet",prof:"OMRON CIO"},
 {v:"OMRON",model:"CJ2M-CPU31",dio:2560,sk:60,us:0.04,cap:"60K 스텝",tm:4096,cn:4096,comm:"USB·Ethernet",prof:"OMRON CIO"},
 {v:"OMRON",model:"NX1P2-1140DT",dio:256,sk:null,us:0.0031,cap:"1.5MB(IEC)",tm:null,cn:null,comm:"EtherCAT·EtherNet/IP",prof:"OMRON NX(IEC)"}];
function estSteps(lad){
  let n=0;
  for(const r of lad.rungs){
    for(const b of r.input_branches)n+=b.elements.length;
    for(const o of r.outputs)n+=(o.element_type==="TIMER"||o.element_type==="COUNTER")?3:2;
  }
  return n;
}
function fitCheck(L,m){
  const io=L.d.sim.inputs.length+L.d.sim.outputs.length;
  const tmr=Object.keys(L.plc.timers).length,cnt=Object.keys(L.plc.counters).length;
  const st2=estSteps(L.d.ladder),iss=[];
  if(io>m.dio)iss.push(`I/O ${io}점 > 최대 ${m.dio}점`);
  if(m.tm!==null&&tmr>m.tm)iss.push(`타이머 ${tmr} > ${m.tm}`);
  if(m.cn!==null&&cnt>m.cn)iss.push(`카운터 ${cnt} > ${m.cn}`);
  if(m.sk!==null&&st2>m.sk*1000)iss.push(`추정 ${st2}스텝 > ${m.cap}`);
  return {io,tmr,cnt,st2,iss};
}
function renderFit(){
  const m=PLC_CATALOG.find(x=>x.model===cur.cpu)||PLC_CATALOG[1];
  const f=fitCheck(cur,m);
  document.getElementById("fitbox").innerHTML=
   `<div>${m.v} <b style="color:#dce4f0">${m.model}</b> · ${m.cap} · I/O ${m.dio}점 · ${m.comm}</div>`+
   `<div>주소체계 ${m.prof} · 본 설계: I/O ${f.io}점 · TON ${f.tmr} · CTU ${f.cnt} · 추정 ${f.st2}스텝</div>`+
   (m.us?`<div>기종 환산 로직 스캔 ≈ <b style="color:#8ec9ff">${(f.st2*m.us).toFixed(2)}µs</b>/사이클 (${m.us}µs/스텝 × ${f.st2}스텝 + I/O 리프레시 별도)</div>`:"")+
   (f.iss.length?f.iss.map(i=>`<div class="bad">⚠ ${i}</div>`).join("")
    :`<div class="ok">✓ 기종 적합 — 한계 내 설계</div>`);
}
function buildPlcSel(){
  const el=document.getElementById("plcsel");
  el.innerHTML='<small style="color:var(--mut)">기종</small>';
  const sel=document.createElement("select");
  PLC_CATALOG.forEach(m=>{
    const o=document.createElement("option");
    o.value=m.model;o.textContent=`${m.v} · ${m.model} (${m.cap})`;
    if(m.model===cur.cpu)o.selected=true;
    sel.appendChild(o);
  });
  sel.onchange=()=>{cur.cpu=sel.value;renderFit();
    logEv("op","PLC 기종 변경 → "+cur.cpu);};
  el.appendChild(sel);
  renderFit();
}

/* D 레지스터 맵 — 설정 SP(HMI 기록) + 공정 데이터(비전·카운트) */
function dRegs(L){
  const r=[];
  if(L.scene.speedCtl)r.push(["D0100","생산속도 설정 SP",()=>Math.round(L.speedF*100),"%","sp"]);
  if(L.scene.ngCtl)r.push(["D0101","불량 주입률 SP",()=>L.ngRate,"%","sp"]);
  if(L.scene.demandCtl)r.push(["D0102","수요 부하 SP",()=>Math.round(L.demandF*100),"%","sp"]);
  if(L.id==="conveyor_divert")r.push(
    ["D0110","비전 검사수량",()=>L.sst.insp,"EA","dt"],
    ["D0111","양품 카운트",()=>L.sst.ok,"EA","dt"],
    ["D0112","불량 카운트",()=>L.sst.ng,"EA","dt"]);
  if(L.id==="count_eject")r.push(
    ["D0110","양품 카운트",()=>L.sst.good,"EA","dt"],
    ["D0111","배출 카운트",()=>L.sst.ejected,"EA","dt"]);
  if(L.scene.prod)r.push(["D0120","생산수량 누계",()=>L.scene.prod(L.sst),"EA","dt"]);
  return r;
}

/* 비전 광학 모델 — 1/1.8" 센서(7.2×5.4mm)·1920×1080 가정 */
function visionCfg(L){
  return L.devCfg["VS-701"]||(L.devCfg["VS-701"]={f:12,wd:300,lux:600});
}
function visionOptics(L){
  const c=visionCfg(L);
  const fovW=7.2*c.wd/c.f, fovH=5.4*c.wd/c.f;
  const res=fovW/1920*1000; /* µm/px */
  const cLux=Math.min(1,c.lux/600);
  const cRes=res<=120?1:Math.max(0.3,120/res);
  const conf=Math.max(0.3,Math.min(1,(0.45+0.55*cLux)*cRes));
  return {fovW,fovH,res,conf};
}

/* 결선도(직배선도) 자동 생성 — 라이브 통전 표시 */
function wiringSvg(L){
  const esc=v=>String(v).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
  const rows=[
    ...L.d.sim.inputs.map(sym=>({sym,dir:"IN"})),
    ...L.d.sim.outputs.map(sym=>({sym,dir:"OUT"}))
  ];
  const RH=30,top=50,W=640,H=top+rows.length*RH+26;
  let g="";
  g+=`<text x="64" y="16" fill="#8b98a8" font-size="11" text-anchor="middle">PLC ${esc(L.cpu||"")}</text>`;
  g+=`<text x="280" y="16" fill="#8b98a8" font-size="11" text-anchor="middle">TB-01 단자대</text>`;
  g+=`<text x="540" y="16" fill="#8b98a8" font-size="11" text-anchor="middle">현장 기기</text>`;
  g+=`<line x1="24" y1="${top-16}" x2="${W-18}" y2="${top-16}" stroke="#b8860b" stroke-width="1.6"/>`;
  g+=`<text x="28" y="${top-21}" fill="#d9a514" font-size="9.5">DC24V COM 모선</text>`;
  g+=`<line x1="${W-18}" y1="${top-16}" x2="${W-18}" y2="${top+rows.length*RH-12}" stroke="#6b5410" stroke-width="1.2" stroke-dasharray="3 3"/>`;
  rows.forEach((r,i)=>{
    const y=top+i*RH+8;
    const on=L.plc.val(r.sym);
    const col=on?(r.dir==="IN"?"#58a6ff":"#3fd97a"):"#33414f";
    const tcol=on?(r.dir==="IN"?"#9cc7ff":"#7ee787"):"#8fa0b3";
    const addr=L.m.addr[r.sym]||"—";
    const wn=(r.dir==="IN"?"W1":"W2")+String(i+1).padStart(2,"0");
    g+=`<rect x="22" y="${y-10}" width="84" height="21" rx="3" fill="#16202b" stroke="#33414f"/>`;
    g+=`<text x="64" y="${y+4}" fill="${tcol}" font-size="10.5" text-anchor="middle" font-family="monospace">${esc(addr)}</text>`;
    g+=`<line x1="106" y1="${y}" x2="252" y2="${y}" stroke="${col}" stroke-width="${on?2.2:1.5}"/>`;
    g+=`<text x="178" y="${y-4}" fill="#6f7a8a" font-size="9" text-anchor="middle" font-family="monospace">${wn}</text>`;
    g+=`<rect x="252" y="${y-10}" width="34" height="21" rx="3" fill="#1d2733" stroke="#3a4756"/>`;
    g+=`<text x="269" y="${y+4}" fill="#9fb3c8" font-size="10" text-anchor="middle" font-family="monospace">${i+1}</text>`;
    g+=`<line x1="286" y1="${y}" x2="468" y2="${y}" stroke="${col}" stroke-width="${on?2.2:1.5}"/>`;
    g+=`<text x="377" y="${y-4}" fill="#6f7a8a" font-size="9" text-anchor="middle" font-family="monospace">${wn}A</text>`;
    const info=L.m.tags&&L.m.tags[r.sym];
    const devName=info?info.tag+" "+info.name:(L.m.desc[r.sym]||r.sym);
    g+=`<rect x="468" y="${y-11}" width="142" height="23" rx="3" fill="#16202b" stroke="${r.dir==="IN"?"#2b4a6e":"#2e6b44"}"/>`;
    g+=`<text x="539" y="${y+4}" fill="${tcol}" font-size="9.5" text-anchor="middle">${esc(devName.slice(0,20))}</text>`;
    g+=`<line x1="610" y1="${y}" x2="${W-18}" y2="${y}" stroke="#6b5410" stroke-width="1" stroke-dasharray="3 3"/>`;
    if(on)g+=`<circle cx="269" cy="${y}" r="3.2" fill="${col}"/>`;
  });
  return `<svg width="100%" viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg" style="max-width:${W}px">${g}</svg>`;
}

/* 설정 드로어 — 기종·운전 파라미터·고장 주입(라인별) */
function buildSettings(){
  document.getElementById("settitle").textContent=OV[cur.id]||cur.d.title;
  buildPlcSel();
  const sl=document.getElementById("setsliders");sl.innerHTML="";
  const mkSlider=(label,id,min,max,val,suffix,oninput)=>{
    const w=document.createElement("div");w.className="sld";
    w.innerHTML=`<small>${label} <b id="${id}v">${val}${suffix}</b></small><input id="${id}" type="range" min="${min}" max="${max}" value="${val}"/>`;
    sl.appendChild(w);
    w.querySelector("input").addEventListener("input",e=>{
      w.querySelector("b").textContent=e.target.value+suffix;
      oninput(+e.target.value);
    });
  };
  if(cur.scene.speedCtl)mkSlider("생산속도","spdr",50,150,Math.round(cur.speedF*100),"%",
    v=>{cur.speedF=v/100;logEv("op","생산속도 변경 → "+v+"%");});
  if(cur.scene.ngCtl)mkSlider("불량 주입률","ngr",0,25,cur.ngRate,"%",
    v=>{cur.ngRate=v;logEv("op","불량 주입률 변경 → "+v+"%");});
  if(cur.scene.demandCtl)mkSlider("수요 부하","dmr",20,170,Math.round(cur.demandF*100),"%",
    v=>{cur.demandF=v/100;logEv("op","공정 수요 부하 변경 → "+v+"%");});
  if(!cur.scene.speedCtl&&!cur.scene.ngCtl&&!cur.scene.demandCtl)
    sl.innerHTML='<span class="hint" style="font-size:12px;color:var(--mut)">이 라인은 조정 파라미터가 없습니다.</span>';
  else{
    const nt=document.createElement("div");
    nt.className="hint";nt.style.cssText="font-size:11.5px;color:var(--mut);width:100%";
    nt.textContent="슬라이더 값은 PLC 설정 레지스터(D0100~)에 기록되어 IO 표에 실시간 표시됩니다.";
    sl.appendChild(nt);
  }
  const ff=document.getElementById("setfaults");ff.innerHTML="";
  (cur.m.faults||[]).forEach(f=>{
    const fb=document.createElement("button");
    fb.className="fbtn"+(cur.faults[f.id]?" on":"");fb.textContent=f.label;
    fb.onclick=()=>{cur.faults[f.id]=!cur.faults[f.id];fb.classList.toggle("on",!!cur.faults[f.id]);
      logEv("warn",f.label+(cur.faults[f.id]?" — 고장 발생(주입)":" — 복구 완료"));};
    ff.appendChild(fb);
  });
  if(!(cur.m.faults||[]).length)
    ff.innerHTML='<span class="hint" style="font-size:12px;color:var(--mut)">이 라인은 고장 주입 항목이 없습니다.</span>';
  /* 통신 I/O 구성 */
  const cm=document.getElementById("setcomm");
  if(cm){
    const vend=(PLC_CATALOG.find(x=>x.model===cur.cpu)||{}).v||"LS";
    const defProto={LS:"XGT FEnet (TCP 2004)",MITSUBISHI:"MELSEC MC (TCP 5007)",
      SIEMENS:"S7/PROFINET (TCP 102)",OMRON:"FINS/EtherNet·IP (TCP 9600)"}[vend];
    if(!cur.comm)cur.comm=defProto;
    const protos=[defProto,"Modbus TCP (502)","EtherNet/IP (44818)","RS-485 시리얼(9600-N-8-1)"];
    const ip="192.168.0."+(10+ids.indexOf(cur.id));
    cm.innerHTML="";
    const sel=document.createElement("select");
    sel.style.cssText="width:100%;background:#0a0f17;border:1px solid var(--bd);color:var(--fg);font:12px ui-monospace,monospace;padding:6px 8px;border-radius:8px";
    [...new Set(protos)].forEach(p2=>{const o=document.createElement("option");
      o.value=p2;o.textContent=p2;if(p2===cur.comm)o.selected=true;sel.appendChild(o);});
    sel.onchange=()=>{cur.comm=sel.value;logEv("op","통신 프로토콜 변경 → "+sel.value);buildSettings();};
    cm.appendChild(sel);
    const inf=document.createElement("div");
    inf.className="fitbox";inf.style.marginTop="8px";
    inf.innerHTML=`가상 스테이션 IP <b style="color:#8ec9ff">${ip}</b> · 기종 포트: ${(PLC_CATALOG.find(x=>x.model===cur.cpu)||{}).comm||"—"}`+
      `<br/>서버 코사임 연동 시 이 채널로 I/O 미러링(섀도 모드 — 로드맵 P2)`;
    cm.appendChild(inf);
  }
  /* 제품·부하 설정 */
  const pr2=document.getElementById("setprod");
  if(pr2){
    const cfg=KPI[cur.id]||(KPI[cur.id]={unit:"개",w:null,tt:null});
    pr2.innerHTML="";
    const mkNum=(label,val,suffix,cb)=>{
      const w=document.createElement("div");w.className="sld";
      w.innerHTML=`<small>${label}</small>`;
      const inp=document.createElement("input");
      inp.type="number";inp.step="0.1";inp.value=val===null?"":val;
      inp.style.cssText="width:110px;background:#0a0f17;border:1px solid var(--bd);color:var(--fg);font:12.5px ui-monospace,monospace;padding:6px 8px;border-radius:8px";
      inp.addEventListener("change",()=>{const v=parseFloat(inp.value);
        if(!isNaN(v)&&v>0){cb(v);logEv("op",label+" 변경 → "+v+suffix);}});
      w.appendChild(inp);pr2.appendChild(w);
    };
    mkNum("개당 중량 kg/"+cfg.unit,cfg.w,"kg",v=>{cfg.w=v;});
    mkNum("목표 택타임 s",cfg.tt,"s",v=>{cfg.tt=v;});
    const nt=document.createElement("div");
    nt.className="hint";nt.style.cssText="font-size:11.5px;color:var(--mut);width:100%";
    nt.textContent="중량은 누적 생산중량 KPI에, 목표 택타임은 OEE 성능(P)·차트 목표선·경보 임계에 즉시 반영됩니다.";
    pr2.appendChild(nt);
  }
}

/* 생산 파라미터 — 제품 단위·개당 중량(kg)·목표 택타임(s) */
const KPI={
 motor_start_stop:{unit:"박스",w:12.5,tt:1.7},
 fwd_rev:{unit:"파레트",w:450,tt:14},
 car_wash:{unit:"대",w:null,tt:9},
 count_eject:{unit:"부품",w:0.8,tt:1.2},
 conveyor_divert:{unit:"부품",w:1.2,tt:2.0},
 weld_cell:{unit:"용접품",w:6.2,tt:13},
 batch_fill_mix_drain:{unit:"배치",w:1800,tt:25},
duty_standby:{unit:"㎥",w:1000,tt:3},
 cascade_conveyor:{unit:"박스",w:8.0,tt:2.1}
};

/* ============================================================
   가상 PLC — 내장 래더 JSON을 매 스캔 순차 평가 (TON·CTU 포함)
   ============================================================ */
function parsePreset(s){const m=/T#(\d+(?:\.\d+)?)(ms|s)/i.exec(s||"");if(!m)return 1;return m[2].toLowerCase()==="ms"?+m[1]/1000:+m[1];}
function makePLC(ladder){
  const rungs=ladder.rungs||[], vars=Object.create(null);
  const timers=Object.create(null), counters=Object.create(null);
  rungs.forEach(r=>(r.outputs||[]).forEach(o=>{
    if(o.element_type==="TIMER")timers[o.symbol]={preset:parsePreset(o.description),acc:0,q:false};
    if(o.element_type==="COUNTER")counters[o.symbol]={preset:parseInt(o.description||"1",10)||1,cnt:0,q:false,prev:false};
  }));
  const val=s=>{
    if(s.endsWith(".Q")){const n=s.slice(0,-2);
      if(timers[n])return timers[n].q; if(counters[n])return counters[n].q; return false;}
    return !!vars[s];
  };
  function scan(dt){
    const t0=performance.now(), en=[];
    for(const r of rungs){
      const branches=r.input_branches.length?r.input_branches:[{elements:[]}];
      let any=false; const brs=[];
      for(const b of branches){
        let p=true; const cum=[];
        for(const el of b.elements){
          const v=val(el.symbol);
          p=p&&(el.element_type==="CONTACT_NC"?!v:v);
          cum.push(p);
        }
        brs.push(cum); if(p)any=true;
      }
      for(const o of (r.outputs||[])){
        const et=o.element_type;
        if(et==="TIMER"){
          const t=timers[o.symbol];
          if(any){t.acc=Math.min(t.acc+dt,t.preset);t.q=t.acc>=t.preset;}
          else{t.acc=0;t.q=false;}
        }else if(et==="COUNTER"){
          const c=counters[o.symbol];
          if(any&&!c.prev)c.cnt++;
          c.prev=any; c.q=c.cnt>=c.preset;
        }else if(et==="COIL_RESET"){
          if(any){const c=counters[o.symbol];
            if(c){c.cnt=0;c.q=false;} else vars[o.symbol]=false;}
        }else if(et==="COIL_SET"){
          if(any)vars[o.symbol]=true;
        }else vars[o.symbol]=any;
      }
      en.push({brs,out:any});
    }
    return {us:(performance.now()-t0)*1000,en};
  }
  return {vars,timers,counters,val,scan,set:(s,v)=>{vars[s]=v;}};
}

/* ============================================================
   통전 래더 렌더러 — 전류 경로 실시간 + TON/CTU 현재값
   ============================================================ */
function ladderLive(ladder,en,plc,addr){
  const LEFT=24,BUSL=70,SLOT=104,ROWH=58,PADT=28,COILW=90;
  const esc=s=>String(s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
  const ON="#3fd97a",OFF="#33414f";
  const ln=(x1,y1,x2,y2,on,w)=>`<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="${on?ON:OFF}" stroke-width="${(w||2)+(on?0.8:0)}"/>`;
  const contact=(cx,cy,el,onp)=>{
    const nc=el.element_type==="CONTACT_NC", bar=onp?"#7ee787":"#9aa7b5", g=[];
    g.push(`<line x1="${cx-6}" y1="${cy-11}" x2="${cx-6}" y2="${cy+11}" stroke="${bar}" stroke-width="2"/>`);
    g.push(`<line x1="${cx+6}" y1="${cy-11}" x2="${cx+6}" y2="${cy+11}" stroke="${bar}" stroke-width="2"/>`);
    if(nc)g.push(`<line x1="${cx-9}" y1="${cy+11}" x2="${cx+9}" y2="${cy-11}" stroke="${bar}" stroke-width="2"/>`);
    g.push(`<text x="${cx}" y="${cy-16}" fill="${onp?"#bff5cd":"#dce4f0"}" font-size="11" text-anchor="middle">${esc(el.symbol)}</text>`);
    const a=(addr&&addr[el.symbol.replace(/\.Q$/,"")])||"";
    if(a)g.push(`<text x="${cx}" y="${cy+26}" fill="#6f7a8a" font-size="10" text-anchor="middle">${esc(a)}</text>`);
    return g.join("");
  };
  const output=(cx,cy,o,on)=>{
    const g=[], et=o.element_type;
    if(et==="TIMER"||et==="COUNTER"){
      const tm=et==="TIMER"?plc&&plc.timers[o.symbol]:null;
      const cn=et==="COUNTER"?plc&&plc.counters[o.symbol]:null;
      const q=!!((tm&&tm.q)||(cn&&cn.q));
      g.push(`<rect x="${cx}" y="${cy-18}" width="${COILW}" height="36" rx="4" fill="#1d2733" stroke="${q?ON:(on?"#4f9dff":"#33414f")}" stroke-width="${q||on?2:1.5}"/>`);
      g.push(`<text x="${cx+COILW/2}" y="${cy-3}" fill="${q?"#7ee787":"#8ec9ff"}" font-size="10" text-anchor="middle">${et==="TIMER"?"TON":"CTU"} ${esc(o.symbol)}</text>`);
      const lab=tm?`${tm.acc.toFixed(1)}s / ${tm.preset}s${q?" ✓Q":""}`
              :cn?`${cn.cnt} / ${cn.preset}${q?" ✓Q":""}`:esc(o.description||"");
      g.push(`<text x="${cx+COILW/2}" y="${cy+12}" fill="#9fb3c8" font-size="10" text-anchor="middle">${lab}</text>`);
      return g.join("");
    }
    const set=et==="COIL_SET",rst=et==="COIL_RESET";
    const c=on?(rst?"#ff8f8f":ON):"#3a4a5a";
    g.push(`<text x="${cx+35}" y="${cy-16}" fill="${on?(rst?"#ffb3b3":"#7ee787"):"#9fb3c8"}" font-size="11" text-anchor="middle">${esc(o.symbol)}${set?" (S)":rst?" (R)":""}</text>`);
    g.push(`<path d="M ${cx} ${cy-12} Q ${cx+14} ${cy} ${cx} ${cy+12}" fill="none" stroke="${c}" stroke-width="${on?2.6:2}"/>`);
    g.push(`<path d="M ${cx+70} ${cy-12} Q ${cx+56} ${cy} ${cx+70} ${cy+12}" fill="none" stroke="${c}" stroke-width="${on?2.6:2}"/>`);
    if(on)g.push(`<circle cx="${cx+35}" cy="${cy}" r="9" fill="rgba(63,217,122,.18)"/>`);
    const a=(addr&&addr[o.symbol])||"";
    if(a)g.push(`<text x="${cx+35}" y="${cy+26}" fill="#6f7a8a" font-size="10" text-anchor="middle">${esc(a)}</text>`);
    return g.join("");
  };
  const rungs=ladder.rungs||[];
  let maxCols=1;
  for(const r of rungs)for(const b of r.input_branches)maxCols=Math.max(maxCols,b.elements.length,1);
  const busR=BUSL+maxCols*SLOT+10, coilX=busR+40, rightRail=coilX+COILW+30, width=rightRail+20;
  let y=0; const parts=[];
  rungs.forEach((rung,ri)=>{
    const e=en&&en[ri], out=!!(e&&e.out);
    const branches=rung.input_branches.length?rung.input_branches:[{elements:[]}];
    const h=branches.length*ROWH+PADT, top=y+PADT;
    const rowYs=branches.map((_,i)=>top+i*ROWH+ROWH/2);
    const p=[];
    p.push(`<text x="${BUSL}" y="${y+17}" fill="#7f8a9a" font-size="11">${esc("["+(ri+1)+"] "+(rung.comment||""))}</text>`);
    p.push(`<line x1="${LEFT}" y1="${y}" x2="${LEFT}" y2="${y+h}" stroke="#d14b4b" stroke-width="3"/>`);
    p.push(`<line x1="${rightRail}" y1="${y}" x2="${rightRail}" y2="${y+h}" stroke="#d14b4b" stroke-width="3"/>`);
    if(branches.length>1){
      p.push(ln(BUSL,rowYs[0],BUSL,rowYs[rowYs.length-1],true,2));
      p.push(ln(busR,rowYs[0],busR,rowYs[rowYs.length-1],out,2));
    }
    p.push(ln(LEFT,rowYs[0],BUSL,rowYs[0],true,2));
    branches.forEach((b,bi)=>{
      const yc=rowYs[bi], cum=(e&&e.brs[bi])||[];
      let x=BUSL, power=true;
      if(!b.elements.length){p.push(ln(BUSL,yc,busR,yc,true,2));return;}
      b.elements.forEach((el,ci)=>{
        const cx=BUSL+ci*SLOT+SLOT/2;
        p.push(ln(x,yc,cx-16,yc,power,2));
        const passed=en?!!cum[ci]:false;
        p.push(contact(cx,yc,el,passed));
        power=passed; x=cx+16;
      });
      p.push(ln(x,yc,busR,yc,power,2));
    });
    const midY=rowYs[0];
    p.push(ln(busR,midY,coilX-16,midY,out,2));
    (rung.outputs||[]).forEach((o,oi)=>{
      const yc=midY+oi*ROWH;
      p.push(output(coilX,yc,o,out));
      p.push(ln(coilX+COILW-16,yc,rightRail,yc,out,2));
    });
    parts.push("<g>"+p.join("")+"</g>"); y+=h;
  });
  return `<svg width="${width}" height="${y+10}" xmlns="http://www.w3.org/2000/svg">${parts.join("")}</svg>`;
}

/* ============================================================
   아이소메트릭 3D 엔진 — 1유닛=1m, 깊이 정렬 렌더 큐(관통 방지)
   ============================================================ */
const cvs=document.getElementById("scene"), g2=cvs.getContext("2d");
const WX=18, WY=7.7;                    // 씬 월드 크기(m)
let view={s:24,ox:0,oy:0,W:0,H:0};
function resize(){
  const dpr=window.devicePixelRatio||1, W=cvs.clientWidth, H=cvs.clientHeight;
  cvs.width=Math.max(1,W*dpr); cvs.height=Math.max(1,H*dpr);
  g2.setTransform(dpr,0,0,dpr,0,0);
  const s=Math.min((W-36)/((WX+WY)*0.866), (H-50)/((WX+WY)*0.5+2.3));
  const ts=Math.min((W-46)/WX,(H-56)/WY);
  view={s,ox:18+WY*0.866*s,oy:42+2.3*0.8*s,W,H,
    ts,tox:(W-WX*ts)/2,toy:(H-WY*ts)/2+8};
}
addEventListener("resize",resize);
let VIEW_MODE="iso";
const P=(x,y,z)=>VIEW_MODE==="top"
  ?[view.tox+x*view.ts, view.toy+y*view.ts-(z||0)*0.12*view.ts]
  :[view.ox+(x-y)*0.866*view.s, view.oy+(x+y)*0.5*view.s-(z||0)*0.8*view.s];
function shade(hex,f){
  const n=parseInt(hex.slice(1),16);
  const r=Math.min(255,(n>>16&255)*f),g=Math.min(255,(n>>8&255)*f),b=Math.min(255,(n&255)*f);
  return `rgb(${r|0},${g|0},${b|0})`;
}
function face(ctx,pts,fill,stroke){
  ctx.beginPath();ctx.moveTo(pts[0][0],pts[0][1]);
  for(let i=1;i<pts.length;i++)ctx.lineTo(pts[i][0],pts[i][1]);
  ctx.closePath();ctx.fillStyle=fill;ctx.fill();
  if(stroke){ctx.strokeStyle=stroke;ctx.lineWidth=0.7;ctx.stroke();}
}
/* 깊이 정렬 큐 — 모든 입체는 여기로 들어가 뒤→앞 순서로 그려진다 */
let DQ=[],LB=[],SH=[],CHIPS=[];
const DEF_POS={op:[12.3,5.05],plc:[14.7,4.9],avr:[15.78,4.95],stg:[2.35,5.9]};
const EDITKEY={"OP-01":"op","PLC-01":"plc","AVR-01":"avr","STG-01":"stg"};
let LAYOUT={};
try{LAYOUT=JSON.parse(localStorage.getItem("hands_layout")||"{}");}catch(e){}
function LP(k){const d=DEF_POS[k],o=LAYOUT[k]||{dx:0,dy:0};return[d[0]+o.dx,d[1]+o.dy];}
let labelMode=1,editMode=false,eDrag=null;
let cam={z:1,px:0,py:0};
let camT={z:1,px:0,py:0};
const dq=(d,f)=>DQ.push({d,f});
function flushQ(ctx){DQ.sort((a,b)=>a.d-b.d);for(const o of DQ)o.f(ctx);DQ.length=0;}
const EDGE="rgba(8,12,16,.35)";
function box3(x,y,z,w,d,h,c){
  dq(x+y+(w+d)*0.5+z*0.02,ctx=>{
    face(ctx,[P(x,y,z+h),P(x+w,y,z+h),P(x+w,y+d,z+h),P(x,y+d,z+h)],shade(c,1.16),EDGE);
    face(ctx,[P(x,y+d,z),P(x+w,y+d,z),P(x+w,y+d,z+h),P(x,y+d,z+h)],shade(c,0.62),EDGE);
    face(ctx,[P(x+w,y,z),P(x+w,y+d,z),P(x+w,y+d,z+h),P(x+w,y,z+h)],shade(c,0.88),EDGE);
  });
}
function cyl3(x,y,z,r,h,c){
  dq(x+y+r+z*0.02,ctx=>{
    const rx=r*1.22*view.s, ry=r*0.62*view.s;
    const b=P(x,y,z), t=P(x,y,z+h);
    ctx.beginPath();
    ctx.moveTo(b[0]-rx,b[1]);ctx.lineTo(t[0]-rx,t[1]);
    ctx.ellipse(t[0],t[1],rx,ry,0,Math.PI,0,false);
    ctx.lineTo(b[0]+rx,b[1]);
    ctx.ellipse(b[0],b[1],rx,ry,0,0,Math.PI,false);
    ctx.closePath();ctx.fillStyle=shade(c,0.74);ctx.fill();
    ctx.strokeStyle=EDGE;ctx.lineWidth=0.7;ctx.stroke();
    ctx.beginPath();ctx.ellipse(t[0],t[1],rx,ry,0,0,7);
    ctx.fillStyle=shade(c,1.18);ctx.fill();ctx.strokeStyle=EDGE;ctx.stroke();
  });
}
function sh(x,y,w,d,a){SH.push({x,y,w,d,a:a||0.26});}
function drawShadows(ctx){
  for(const s of SH)
    face(ctx,[P(s.x-0.06,s.y-0.04,0),P(s.x+s.w+0.18,s.y-0.04,0),P(s.x+s.w+0.18,s.y+s.d+0.2,0),P(s.x-0.06,s.y+s.d+0.2,0)],`rgba(0,0,0,${s.a})`);
  SH.length=0;
}
function seg(ctx,a,b,st,w){ctx.strokeStyle=st;ctx.lineWidth=w||1;ctx.beginPath();ctx.moveTo(a[0],a[1]);ctx.lineTo(b[0],b[1]);ctx.stroke();}
function lamp(ctx,p,r,c,on){
  if(on){ctx.save();ctx.shadowColor=c;ctx.shadowBlur=12;}
  ctx.beginPath();ctx.arc(p[0],p[1],r,0,7);ctx.fillStyle=on?c:"#1a2330";ctx.fill();
  ctx.strokeStyle="rgba(255,255,255,.25)";ctx.lineWidth=0.8;ctx.stroke();
  if(on)ctx.restore();
}
function txt(ctx,p,s,c,size,align,bold){
  ctx.fillStyle=c||"#8b98a8";ctx.font=(bold?"700 ":"")+(size||11)+"px ui-monospace,monospace";
  ctx.textAlign=align||"center";ctx.fillText(s,p[0],p[1]);
}
/* 기기 태그 라벨(스크린 공간 칩) */
function tag3(x,y,z,tg,sub,c,pr){LB.push({x,y,z,tg,sub,c,pr:pr||1});}
function drawLabels(ctx){
  const placed=[];
  LB.sort((a,b)=>(a.x+a.y)-(b.x+b.y));
  for(const l of LB){
    const editable=editMode&&EDITKEY[l.tg];
    if(!editable){
      if(labelMode===0)continue;
      if(labelMode===1&&l.pr===2)continue;
    }
    const p=P(l.x,l.y,l.z), w=Math.max(44,l.tg.length*7.2,(l.sub||"").length*5.6)+12, h=l.sub?26:17;
    let by=p[1]-h-12, guard=0;
    while(guard++<10&&placed.some(r=>Math.abs(p[0]-r.cx)<(w+r.w)/2+5&&by<r.by+r.h+3&&by+h>r.by-3))by=Math.min(by,placed.reduce((m,r)=>Math.abs(p[0]-r.cx)<(w+r.w)/2+5?Math.min(m,r.by):m,by))-h-5;
    placed.push({cx:p[0],w,by,h});
    const bx=p[0]-w/2;
    CHIPS.push({bx,by,w,h,ax:p[0],ay:p[1],tg:l.tg,sub:l.sub});
    seg(ctx,[p[0],p[1]],[p[0],by+h],"rgba(160,180,200,.35)",1);
    ctx.beginPath();ctx.roundRect(bx,by,w,h,4);
    ctx.fillStyle="rgba(13,18,25,.82)";ctx.fill();
    if(editMode&&EDITKEY[l.tg]){
      ctx.setLineDash([4,3]);ctx.strokeStyle="#58a6ff";ctx.lineWidth=1.6;ctx.stroke();ctx.setLineDash([]);
    }else{ctx.strokeStyle=l.c||"#3a4756";ctx.lineWidth=1;ctx.stroke();}
    txt(ctx,[p[0],by+11.5],l.tg,l.c||"#dce4f0",9.5,"center",true);
    if(l.sub)txt(ctx,[p[0],by+22],l.sub,"#7f8a9a",8.5);
  }
  LB.length=0;
}
/* LED 생산표시판 */
function ledBoard(x,y,label,value,c){
  box3(x-0.04,y-0.04,0,0.08,0.08,2.0,"#2a3340");
  box3(x-0.75,y-0.05,2.0,1.5,0.1,0.62,"#10161e");
  dq(x+y+99,ctx=>{
    const p=P(x,y,2.31);
    txt(ctx,[p[0],p[1]-8],label,"#6f7a8a",9.5);
    ctx.save();ctx.shadowColor=c||"#7ee787";ctx.shadowBlur=10;
    txt(ctx,[p[0],p[1]+9],value,c||"#7ee787",15,"center",true);
    ctx.restore();
  });
}
/* 배선(바닥 트레이) */
function wirePath(ctx,pts,on,t,color){
  ctx.save();ctx.lineCap="round";ctx.lineJoin="round";
  ctx.beginPath();
  const p0=P(pts[0][0],pts[0][1],0.03);ctx.moveTo(p0[0],p0[1]);
  for(let i=1;i<pts.length;i++){const p=P(pts[i][0],pts[i][1],0.03);ctx.lineTo(p[0],p[1]);}
  ctx.strokeStyle="rgba(150,170,190,.14)";ctx.lineWidth=2.6;ctx.stroke();
  if(on){
    ctx.strokeStyle=color;ctx.lineWidth=2;
    ctx.shadowColor=color;ctx.shadowBlur=8;
    ctx.setLineDash([6,9]);ctx.lineDashOffset=-(t*42)%15;
    ctx.stroke();
  }
  ctx.restore();
}
/* 공장 바닥 — 콘크리트 타일 + 통로 라인 */
function floorGrid(ctx){
  if(VIEW_MODE!=="top"){
  face(ctx,[P(0,0,0),P(WX,0,0),P(WX,0,3.9),P(0,0,3.9)],"#151b23");
  for(let x=0.8;x<WX-1;x+=2.2)
    face(ctx,[P(x,0,2.35),P(x+1.5,0,2.35),P(x+1.5,0,3.35),P(x,0,3.35)],"rgba(140,180,220,.07)");
  seg(ctx,P(0,0,2.2),P(WX,0,2.2),"rgba(0,0,0,.35)",1);
  face(ctx,[P(13.1,0,1.45),P(16.3,0,1.45),P(16.3,0,2.05),P(13.1,0,2.05)],"#16241a");
  txt(ctx,P(14.7,0,1.7),"무재해 247日","#7ee787",12,"center",true);
  }
  face(ctx,[P(0,0,0),P(WX,0,0),P(WX,WY,0),P(0,WY,0)],"#20262e");
  for(let x=0;x<=WX;x+=2)seg(ctx,P(x,0,0),P(x,WY,0),"rgba(0,0,0,.22)",1);
  for(let y=0;y<=WY;y+=2)seg(ctx,P(0,y,0),P(WX,y,0),"rgba(0,0,0,.22)",1);
  seg(ctx,P(0.4,4.75,0.01),P(WX-0.4,4.75,0.01),"rgba(217,165,20,.5)",2);
  seg(ctx,P(0.4,6.7,0.01),P(WX-0.4,6.7,0.01),"rgba(217,165,20,.5)",2);
  for(let x=1;x<WX-1;x+=1.2)seg(ctx,P(x,5.72,0.01),P(x+0.6,5.72,0.01),"rgba(217,165,20,.28)",1.5);
  for(let x=1.4;x<11.6;x+=0.8){
    seg(ctx,P(x,6.12,0.012),P(x+0.4,6.12,0.012),"rgba(88,224,255,.30)",1.4);
    seg(ctx,P(x,5.3,0.012),P(x+0.4,5.3,0.012),"rgba(126,224,168,.28)",1.4);
  }
}
/* 안전펜스 — 높이 1.4m (ISO 13857) */
function fence(x0,y0,x1,y1,gap){
  const post=(x,y)=>{box3(x-0.035,y-0.035,0,0.07,0.07,1.4,"#caa011");};
  const rail=(a,b)=>dq((a[0]+a[1]+b[0]+b[1])/2+0.9,ctx=>{
    seg(ctx,P(a[0],a[1],1.36),P(b[0],b[1],1.36),"#caa011",2);
    seg(ctx,P(a[0],a[1],0.72),P(b[0],b[1],0.72),"#2b333d",1.6);
    seg(ctx,P(a[0],a[1],0.12),P(b[0],b[1],0.12),"#caa011",1.6);
    const n=Math.ceil(Math.hypot(b[0]-a[0],b[1]-a[1])/0.28);
    for(let i=1;i<n;i++){
      const fx=a[0]+(b[0]-a[0])*i/n, fy=a[1]+(b[1]-a[1])*i/n;
      seg(ctx,P(fx,fy,0.12),P(fx,fy,1.36),"rgba(120,135,150,.30)",0.8);
    }
  });
  for(let x=x0;x<=x1+0.01;x+=Math.max(1,(x1-x0)/Math.round(x1-x0)))post(x,y0),post(x,y1);
  for(let y=y0;y<=y1+0.01;y+=Math.max(1,(y1-y0)/Math.round(y1-y0)))post(x0,y),post(x1,y);
  rail([x0,y0],[x1,y0]);
  rail([x0,y0],[x0,y1]);rail([x1,y0],[x1,y1]);
  if(gap==="front"){rail([x0,y1],[x0+(x1-x0)*0.3,y1]);rail([x1-(x1-x0)*0.3,y1],[x1,y1]);}
  else rail([x0,y1],[x1,y1]);
}
/* 작업자(키 1.75m — 스케일 기준) */
function worker(x,y,t){
  const sw=t!==undefined?Math.sin(t*7)*0.09:0;
  sh(x-0.25,y-0.2,0.5,0.4,0.2);
  box3(x-0.13+sw,y-0.15,0,0.11,0.13,0.78,"#2b3440");
  box3(x+0.02-sw,y-0.15,0,0.11,0.13,0.78,"#2b3440");
  box3(x-0.18,y-0.17,0.78,0.36,0.24,0.62,"#33567f");
  dq(x+y+1.5,ctx=>{
    const h=P(x,y,1.56);
    ctx.beginPath();ctx.arc(h[0],h[1],0.095*1.1*view.s,0,7);ctx.fillStyle="#d4a982";ctx.fill();
    ctx.beginPath();ctx.arc(h[0],h[1]-0.04*view.s,0.1*1.1*view.s,Math.PI,0);ctx.fillStyle="#e8c413";ctx.fill();
  });
}
/* 자재 랙(배경 스케일감) */
function rack(x,y,bays){
  for(let i=0;i<=bays;i++)box3(x+i*1.35,y,0,0.09,0.8,2.6,"#3d4854");
  for(const z of[0.9,1.75,2.55])
    dq(x+y+bays*0.7,ctx=>{seg(ctx,P(x,y+0.06,z),P(x+bays*1.35,y+0.06,z),"#506070",2);seg(ctx,P(x,y+0.76,z),P(x+bays*1.35,y+0.76,z),"#506070",2);});
  for(let i=0;i<bays;i++)for(const z of[0.92,1.77])
    if((i+z*7|0)%3!==0)box3(x+0.2+i*1.35,y+0.1,z,0.95,0.6,0.55,["#41506188","#4a455e","#3f5a51","#5e5340"][(i+(z>1?1:0))%4]);
}
/* 컨베이어 유닛 — 작업높이 0.75m·벨트폭 0.6m(실측 비율) */
function beltUnit(x0,y0,len,phase,running,zTop){
  const z=(zTop||0.75)-0.13, wd=0.62;
  sh(x0,y0,len,wd,0.24);
  for(let lx=x0+0.25;lx<x0+len;lx+=1.9){
    box3(lx,y0+0.06,0,0.09,0.09,z,"#39434f");
    box3(lx,y0+wd-0.15,0,0.09,0.09,z,"#39434f");
  }
  box3(x0,y0,z,len,0.07,0.13,"#274b73");
  box3(x0,y0+wd-0.07,z,len,0.07,0.13,"#274b73");
  dq(x0+y0+len*0.5+wd*0.5+z*0.02+0.01,ctx=>{
    face(ctx,[P(x0,y0+0.07,z+0.11),P(x0+len,y0+0.07,z+0.11),P(x0+len,y0+wd-0.07,z+0.11),P(x0,y0+wd-0.07,z+0.11)],"#11151b",EDGE);
    const step=0.55;
    for(let i=0;i<len/step+1;i++){
      const fx=x0+((i*step+phase)%len);
      seg(ctx,P(fx,y0+0.1,z+0.115),P(fx,y0+wd-0.1,z+0.115),"rgba(200,215,230,.10)",1.2);
    }
  });
  box3(x0-0.12,y0+0.1,z-0.02,0.12,wd-0.2,0.16,"#3a4654");
  box3(x0+len,y0+0.1,z-0.02,0.12,wd-0.2,0.16,"#3a4654");
}
/* 시그널 타워(적·황·녹) */
function stackLight(x,y,r,a,g){
  box3(x-0.025,y-0.025,0,0.05,0.05,1.1,"#222a34");
  dq(x+y+1.2,ctx=>{
    lamp(ctx,P(x,y,1.34),3.4,"#f85149",r);
    lamp(ctx,P(x,y,1.24),3.4,"#d9a514",a);
    lamp(ctx,P(x,y,1.14),3.4,"#3fb950",g);
  });
}
/* 제어 구역(공통): 조작 페데스탈 + PLC 캐비닛(0.8×0.45×1.9m) + 작업자 */
function forklift(t){
  const ph=(t/34)%1, tri=2*Math.abs(ph-0.5);
  const fx=2.2+9.8*(1-tri), fy=6.85, fwd=ph<0.5;
  sh(fx-0.7,fy-0.55,1.6,1.1,0.26);
  box3(fx-0.55,fy-0.45,0.18,1.25,0.95,0.55,"#c98a16");
  box3(fx+0.18,fy-0.3,0.73,0.5,0.65,0.55,"#8a5e0e");
  box3(fx-0.42,fy-0.38,0,0.3,0.22,0.2,"#11161d");
  box3(fx+0.42,fy-0.38,0,0.3,0.22,0.2,"#11161d");
  box3(fx-0.42,fy+0.28,0,0.3,0.22,0.2,"#11161d");
  box3(fx+0.42,fy+0.28,0,0.3,0.22,0.2,"#11161d");
  const mx=fwd?fx-0.78:fx+0.7;
  box3(mx,fy-0.4,0,0.09,0.09,1.35,"#3a4654");
  box3(mx,fy+0.26,0,0.09,0.09,1.35,"#3a4654");
  const fz=0.12;
  box3(fwd?mx-0.55:mx+0.09,fy-0.34,fz,0.55,0.1,0.06,"#9aa7b5");
  box3(fwd?mx-0.55:mx+0.09,fy+0.22,fz,0.55,0.1,0.06,"#9aa7b5");
  if(fwd){
    box3(mx-0.6,fy-0.4,fz+0.06,0.62,0.78,0.1,"#5a4a30");
    box3(mx-0.52,fy-0.3,fz+0.16,0.46,0.6,0.42,"#7a5c2e");
  }
  dq(fx+fy+1.6,c2=>lamp(c2,P(fx+0.4,fy-0.25,1.32),2.4,"#d9a514",(t*2%1)<0.5));
  tag3(fx,fy,1.6,"FL-01","지게차 운행","#d9a514",2);
}

/* 끝단 정지(드웰) 포함 왕복 — 0..1 */
function shuttleWave(t,period,dwell){
  const ph=(t/period)%1, tri=2*Math.abs(ph-0.5);
  return Math.min(1,Math.max(0,(tri-dwell)/(1-2*dwell)));
}
/* AGV-01 중량형(평판 2t) — 자기유도선 주행 */
function agvHeavy(t){
  const w=shuttleWave(t+8,44,0.06);
  const x=1.9+9.3*w, y=6.12;
  sh(x-0.9,y-0.6,1.8,1.2,0.26);
  box3(x-0.85,y-0.55,0,1.7,1.1,0.34,"#2e5e8e");
  box3(x-0.92,y-0.5,0.08,0.1,1.0,0.18,"#d9a514");
  box3(x+0.82,y-0.5,0.08,0.1,1.0,0.18,"#d9a514");
  box3(x-0.6,y-0.4,0.34,1.2,0.8,0.12,"#3a4654");
  box3(x-0.55,y-0.35,0.46,1.1,0.7,0.42,"#52606e");
  dq(x+y+1.2,c2=>{
    seg(c2,P(x-0.55,y,0.66),P(x+0.55,y,0.66),"rgba(20,26,33,.85)",2);
    seg(c2,P(x-0.55,y,0.78),P(x+0.55,y,0.78),"rgba(20,26,33,.85)",2);
  });
  cyl3(x+0.62,y-0.38,0.34,0.08,0.14,"#1a212b");
  dq(x+y+1.4,c2=>{
    lamp(c2,P(x+0.62,y-0.38,0.52),2.6,"#58e0ff",(t*3%1)<0.6);
    lamp(c2,P(x-0.7,y+0.4,0.4),2.2,"#3fb950",true);
  });
  tag3(x,y,1.05,"AGV-01","중량형 AGV 2t","#58e0ff",2);
}
/* AGV-02 지게차형(무인 포크) */
function agvFork(t){
  const w=shuttleWave(t,38,0.07);
  const x=11.3-9.4*w, y=5.3, fwd=((t/38)%1)<0.5;
  sh(x-0.6,y-0.5,1.3,1.0,0.24);
  box3(x-0.5,y-0.42,0.12,1.05,0.88,0.5,"#2f8f6a");
  box3(x-0.56,y-0.36,0,0.26,0.2,0.18,"#11161d");
  box3(x+0.32,y-0.36,0,0.26,0.2,0.18,"#11161d");
  box3(x-0.56,y+0.26,0,0.26,0.2,0.18,"#11161d");
  box3(x+0.32,y+0.26,0,0.26,0.2,0.18,"#11161d");
  const mx=x-0.72;
  box3(mx,y-0.36,0,0.08,0.08,1.25,"#3a4654");
  box3(mx,y+0.24,0,0.08,0.08,1.25,"#3a4654");
  box3(mx-0.5,y-0.3,0.12,0.5,0.09,0.06,"#9aa7b5");
  box3(mx-0.5,y+0.18,0.12,0.5,0.09,0.06,"#9aa7b5");
  if(!fwd){
    box3(mx-0.55,y-0.36,0.18,0.56,0.72,0.1,"#5a4a30");
    box3(mx-0.48,y-0.27,0.28,0.42,0.55,0.4,"#6e532a");
  }
  cyl3(x+0.3,y-0.3,0.62,0.07,0.12,"#1a212b");
  dq(x+y+1.5,c2=>lamp(c2,P(x+0.3,y-0.3,0.78),2.4,"#58e0ff",(t*3.4%1)<0.6));
  tag3(x,y,1.5,"AGV-02","지게차형 AGV","#7ee0a8",2);
}

/* 천장형 웨이퍼 이송(OHT/AMHS) — 정밀 라인 프로파일 */
function ohtKey(ph){
  const SEG=[
    {a:0.00,b:0.24,x0:0.9,x1:5},
    {a:0.24,b:0.40,stop:5},
    {a:0.40,b:0.62,x0:5,x1:11},
    {a:0.62,b:0.78,stop:11},
    {a:0.78,b:1.00,x0:11,x1:16.2}
  ];
  for(const k of SEG){
    if(ph<k.a||ph>=k.b)continue;
    const p=(ph-k.a)/(k.b-k.a);
    if(k.stop!==undefined){
      const h=p<0.35?p/0.35:p>0.65?(1-p)/0.35:1;
      return {x:k.stop,h:Math.max(0,Math.min(1,h)),busy:true};
    }
    const e=p*p*(3-2*p);
    return {x:k.x0+(k.x1-k.x0)*e,h:0,busy:false};
  }
  return {x:0.9,h:0,busy:false};
}
function ohtSystem(t){
  /* 레일 + 천장 행거 */
  box3(0.8,2.26,3.28,15.5,0.1,0.12,"#4a5663");
  dq(3,c2=>{for(let x=1.6;x<16.2;x+=3)seg(c2,P(x,2.31,3.4),P(x,2.31,3.78),"#33404e",1.4);});
  /* FFU 클린룸 천장 필터 */
  for(let x=2.2;x<15.5;x+=3.6){
    box3(x,1.85,3.6,1.7,0.95,0.08,"#243140");
    dq(x+2.3+3.6,c2=>{const p=P(x+0.85,2.32,3.58);
      c2.fillStyle="rgba(120,180,255,.06)";
      c2.beginPath();c2.moveTo(p[0]-22,p[1]);c2.lineTo(p[0]+22,p[1]);
      c2.lineTo(p[0]+13,p[1]+34);c2.lineTo(p[0]-13,p[1]+34);c2.closePath();c2.fill();});
  }
  /* 로드포트 2개 */
  for(const px of[5,11]){
    box3(px-0.24,2.16,1.02,0.48,0.32,0.07,"#33404e");
    dq(px+2.3+1.2,c2=>lamp(c2,P(px,2.32,1.14),2,"#8ec9ff",true));
    tag3(px,2.32,0.98,px===5?"LP-01":"LP-02","로드포트","#8ec9ff",2);
  }
  /* 천장 스토커(FOUP 버퍼) */
  box3(13.85,2.06,2.45,0.95,0.42,0.75,"#2b3743");
  box3(13.95,2.12,2.52,0.32,0.3,0.28,"#cfd6df");
  box3(14.4,2.12,2.52,0.32,0.3,0.28,"#cfd6df");
  tag3(14.3,2.27,3.35,"STK-01","천장 스토커","#9fb3c8",2);
  /* OHT 비히클 2대 — 주행→정지→권하강→권상승 */
  [0,0.5].forEach((off,vi)=>{
    const k=ohtKey(((t/36)+off)%1);
    const vx=k.x, fz=2.96-1.72*k.h;
    box3(vx-0.24,2.2,3.0,0.48,0.22,0.26,"#314153");
    box3(vx-0.26,2.19,3.24,0.52,0.24,0.06,"#4a5663");
    dq(vx+2.3+3.1,c2=>{
      seg(c2,P(vx-0.1,2.31,3.0),P(vx-0.1,2.31,fz+0.32),"#9aa7b5",1);
      seg(c2,P(vx+0.1,2.31,3.0),P(vx+0.1,2.31,fz+0.32),"#9aa7b5",1);
      lamp(c2,P(vx+0.2,2.2,3.12),1.8,k.busy?"#d9a514":"#3fb950",(t*3%1)<0.6);
    });
    box3(vx-0.17,2.21,fz,0.34,0.2,0.32,"#cfd6df");
    box3(vx-0.17,2.19,fz+0.05,0.34,0.03,0.22,"#8b98a8");
    tag3(vx,2.31,3.85,"OHT-0"+(vi+1),"웨이퍼 이송(FOUP)","#9fd0ff",2);
  });
}

function chrome(ctx,t,val){
  const [opx,opy]=LP("op"),[plx,ply]=LP("plc"),[avx,avy]=LP("avr"),[sgx,sgy]=LP("stg");
  /* 조작반 OP-01 */
  sh(opx,opy,0.4,0.4,0.22);
  box3(opx,opy,0,0.36,0.36,1.0,"#252e39");
  box3(opx-0.04,opy-0.04,1.0,0.44,0.44,0.1,"#1c242e");
  cur.m.buttons.forEach((b,i)=>{
    dq(opx+opy+2.5,c2=>lamp(c2,P(opx+0.08+i*0.15,opy+0.08,1.13),2.6,b.c,val(b.sym)));
  });
  tag3(opx+0.18,opy+0.18,1.1,"OP-01","조작반","#8b98a8");
  /* CP-01 제어반 외함(0.8×0.46×1.9m) — 내부: DIN레일 PLC 모듈·배선덕트·단자대 */
  sh(plx,ply,0.85,0.5,0.24);
  box3(plx,ply,0,0.82,0.46,1.9,"#232b36");
  dq(plx+ply+1.97,c2=>{
    /* 내부 백패널(전면 개방) */
    face(c2,[P(plx+0.06,ply+0.46,0.1),P(plx+0.76,ply+0.46,0.1),P(plx+0.76,ply+0.46,1.82),P(plx+0.06,ply+0.46,1.82)],"#39424d",EDGE);
    /* 배선 덕트(슬롯형, 연회색) — 세로2 + 가로2 */
    for(const dx of[0.09,0.66])
      face(c2,[P(plx+dx,ply+0.47,0.18),P(plx+dx+0.07,ply+0.47,0.18),P(plx+dx+0.07,ply+0.47,1.74),P(plx+dx,ply+0.47,1.74)],"#aeb6bf",EDGE);
    for(const dz of[0.95,1.5])
      face(c2,[P(plx+0.09,ply+0.47,dz),P(plx+0.73,ply+0.47,dz),P(plx+0.73,ply+0.47,dz+0.07),P(plx+0.09,ply+0.47,dz+0.07)],"#aeb6bf",EDGE);
    /* DIN 레일 + PLC 모듈열(실물 비율 — CPU 0.12kg 소형 모듈) */
    face(c2,[P(plx+0.18,ply+0.47,1.22),P(plx+0.64,ply+0.47,1.22),P(plx+0.64,ply+0.47,1.25),P(plx+0.18,ply+0.47,1.25)],"#5d6c7c");
    const vend=(PLC_CATALOG.find(x=>x.model===cur.cpu)||{}).v||"LS";
    const cpuCol={LS:"#e3e0d5",MITSUBISHI:"#2a3550",SIEMENS:"#9aa48f",OMRON:"#23262b"}[vend]||"#e3e0d5";
    face(c2,[P(plx+0.165,ply+0.475,1.13),P(plx+0.205,ply+0.475,1.13),P(plx+0.205,ply+0.475,1.34),P(plx+0.165,ply+0.475,1.34)],"#f0c050",EDGE); /* SMPS */
    face(c2,[P(plx+0.215,ply+0.475,1.12),P(plx+0.275,ply+0.475,1.12),P(plx+0.275,ply+0.475,1.35),P(plx+0.215,ply+0.475,1.35)],cpuCol,EDGE);   /* CPU */
    for(let k=0;k<4;k++)
      face(c2,[P(plx+0.285+k*0.075,ply+0.475,1.13),P(plx+0.345+k*0.075,ply+0.475,1.13),P(plx+0.345+k*0.075,ply+0.475,1.33),P(plx+0.285+k*0.075,ply+0.475,1.33)],"#dfe3e8",EDGE); /* I/O 모듈 */
    lamp(c2,P(plx+0.235,ply+0.48,1.31),1.6,"#3fb950",true);
    lamp(c2,P(plx+0.255,ply+0.48,1.31),1.6,"#58a6ff",(t*5%1)<0.5);
    /* 단자대 2열(녹색) + 결선점 */
    for(const dz of[0.36,0.52]){
      face(c2,[P(plx+0.12,ply+0.47,dz),P(plx+0.7,ply+0.47,dz),P(plx+0.7,ply+0.47,dz+0.09),P(plx+0.12,ply+0.47,dz+0.09)],"#2f6b4f",EDGE);
      for(let k=0;k<9;k++){const p=P(plx+0.16+k*0.062,ply+0.475,dz+0.045);
        c2.beginPath();c2.arc(p[0],p[1],1.1,0,7);c2.fillStyle="#cfd6df";c2.fill();}
    }
  });
  tag3(plx+0.4,ply+0.23,2.02,"CP-01","제어반 외함 0.8×1.9m","#8b98a8",2);
  tag3(plx+0.24,ply+0.3,1.5,"PLC-01",(cur.cpu||"XGK")+" 모듈(0.12kg)","#7ee787");
  /* 단자함 TB-01 + 바닥 케이블 덕트(기계측 결선 경유) */
  box3(10.84,4.56,0,0.1,0.1,0.34,"#39434f");
  box3(10.74,4.5,0.34,0.34,0.16,0.46,"#2f3a46");
  dq(10.9+4.6+1,c2=>lamp(c2,P(10.91,4.66,0.72),1.8,"#8ec9ff",true));
  tag3(10.91,4.62,1.0,"TB-01","단자함(현장 결선)","#8ec9ff",2);
  (function(){
    const x0=Math.min(11.1,plx-0.1), x1=Math.max(11.1,plx+0.1);
    box3(Math.min(10.9,plx+0.2),4.58,0,Math.abs(plx+0.3-10.9)+0.2,0.12,0.08,"#333d49");
  })();
  /* AVR-01 */
  sh(avx-0.03,avy-0.03,0.7,0.5,0.24);
  box3(avx,avy,0,0.62,0.46,1.6,"#222d3a");
  dq(avx+avy+1.9,c2=>{
    face(c2,[P(avx+0.07,avy+0.46,0.95),P(avx+0.55,avy+0.46,0.95),P(avx+0.55,avy+0.46,1.45),P(avx+0.07,avy+0.46,1.45)],"rgba(8,12,18,.92)",EDGE);
    const vv=(380+4*Math.sin(t*1.7)+2*Math.sin(t*5.3)).toFixed(0);
    c2.save();c2.shadowColor="#f0c26b";c2.shadowBlur=7;
    txt(c2,P(avx+0.31,avy+0.46,1.22),vv+"V","#f0c26b",10.5,"center",true);
    c2.restore();
    lamp(c2,P(avx+0.15,avy+0.46,0.82),2.2,"#3fb950",true);
    lamp(c2,P(avx+0.31,avy+0.46,0.82),2.2,"#d9a514",(t*1.3%1)<0.15);
  });
  tag3(avx+0.31,avy+0.23,1.75,"AVR-01","자동전압조정기 380V","#f0c26b");
  /* AMR-01 */
  (function(){
    const w2=shuttleWave(t+4,30,0.08);
    const ax=8.2+3.2*w2, ay=4.95;
    sh(ax-0.35,ay-0.3,0.7,0.6,0.2);
    cyl3(ax,ay,0,0.32,0.26,"#3a4f66");
    box3(ax-0.26,ay-0.22,0.26,0.52,0.44,0.07,"#2b3743");
    box3(ax-0.18,ay-0.16,0.33,0.36,0.32,0.22,"#7a5c2e");
    dq(ax+ay+0.9,c2=>lamp(c2,P(ax+0.22,ay-0.18,0.3),2.2,"#58e0ff",(t*4%1)<0.5));
    tag3(ax,ay,0.85,"AMR-01","자율이동로봇","#9fd0ff",2);
  })();
  const tri26=2*Math.abs((t/26)%1-0.5);
  worker(3.6+5.2*(1-tri26),5.78,t);
  worker(13.5,5.7);
  rack(0.6,0.25,4);
  forklift(t);
  agvHeavy(t);
  agvFork(t);
  /* 자재 스테이징(STG-01 — 이동 가능 그룹) */
  sh(sgx-0.05,sgy-0.05,1.3,1.1,0.22);
  box3(sgx,sgy,0,1.2,1.0,0.12,"#5a4a30");
  box3(sgx+0.1,sgy+0.1,0.12,0.45,0.42,0.42,"#6e532a");
  box3(sgx+0.6,sgy+0.1,0.12,0.45,0.42,0.42,"#7a5c2e");
  box3(sgx+0.35,sgy+0.1,0.54,0.45,0.42,0.4,"#65512f");
  tag3(sgx+0.6,sgy+0.3,1.05,"STG-01","자재 스테이징","#6f7a8a");
  sh(5.3,5.95,1.45,0.95,0.2);
  cyl3(5.5,6.35,0,0.3,0.85,"#2e5e8e");cyl3(6.2,6.4,0,0.3,0.85,"#3a6a52");cyl3(5.85,5.98,0,0.3,0.85,"#71583a");
  sh(8.3,5.9,1.3,1.05,0.2);
  box3(8.35,5.95,0,1.2,1.0,0.12,"#5a4a30");
  box3(8.5,6.05,0.12,0.9,0.75,0.55,"#414f61");

  /* ── 상위(천장) 인프라 ── */
  for(const cx2 of[0.5,4.5,8.5,12.5,16.5])
    box3(cx2-0.12,0.06,0,0.24,0.28,3.85,"#27313c");
  dq(1.5,c2=>{
    for(let x=0.5;x<16.4;x+=4){
      seg(c2,P(x,0.2,3.85),P(Math.min(x+4,16.5),0.2,3.85),"#33404e",2.5);
      seg(c2,P(x,0.2,3.45),P(Math.min(x+4,16.5),0.2,3.45),"#2b3743",2);
      for(let k=0;k<4;k++){
        seg(c2,P(x+k,0.2,3.45),P(x+k+0.5,0.2,3.85),"#2b3743",1.2);
        seg(c2,P(x+k+0.5,0.2,3.85),P(Math.min(x+k+1,16.5),0.2,3.45),"#2b3743",1.2);
      }
    }
  });
  box3(0.4,0.62,2.95,16.3,0.5,0.32,"#39434f");
  dq(2,c2=>{
    for(const[zz,col]of[[2.62,"#566472"],[2.5,"#2b86c8"],[2.76,"#b8742c"]])
      seg(c2,P(0.4,0.55,zz),P(16.7,0.55,zz),col,2.2);
    for(let x=1.5;x<16.5;x+=2.5)seg(c2,P(x,0.55,2.82),P(x,0.55,3.45),"#33404e",1.4);
  });
  box3(0.4,1.05,3.78,16.3,0.12,0.1,"#2b3743");
  box3(0.4,4.36,3.78,16.3,0.12,0.1,"#2b3743");
  for(let x=2;x<16.4;x+=3.5)for(const ly of[1.1,4.42]){
    dq(x+ly+3.6,c2=>{
      seg(c2,P(x,ly,3.78),P(x,ly,3.55),"#2b3743",1.2);
      const p=P(x,ly,3.55);
      c2.beginPath();c2.moveTo(p[0]-6,p[1]);c2.lineTo(p[0]+6,p[1]);
      c2.lineTo(p[0]+3,p[1]+5);c2.lineTo(p[0]-3,p[1]+5);c2.closePath();
      c2.fillStyle="#222b35";c2.fill();
      lamp(c2,[p[0],p[1]+6.5],2.4,"#ffe9b8",true);
    });
  }
  /* 공장 상황별 상위 프로파일: oht(정밀)/crane(중량)/piping(프로세스) */
  const ov=cur.scene.overhead||"crane";
  if(ov==="oht")ohtSystem(t);
  /* CR-01 천장 크레인(후면 베이) — 권상 사이클 */
  if(ov==="crane")(function(){
    const ph=(t/52)%1, x1=2.6, x2=13.4;
    const sgm=(a,b)=>Math.min(1,Math.max(0,(ph-a)/(b-a)));
    let bx,hz,load;
    if(ph<0.08){bx=x1;hz=2.85-2.25*sgm(0,0.08);load=false;}
    else if(ph<0.16){bx=x1;hz=0.6+2.25*sgm(0.08,0.16);load=true;}
    else if(ph<0.5){bx=x1+(x2-x1)*sgm(0.16,0.5);hz=2.85;load=true;}
    else if(ph<0.58){bx=x2;hz=2.85-2.25*sgm(0.5,0.58);load=true;}
    else if(ph<0.66){bx=x2;hz=0.6+2.25*sgm(0.58,0.66);load=false;}
    else{bx=x2-(x2-x1)*sgm(0.66,1);hz=2.85;load=false;}
    box3(0.4,0.28,3.02,16.3,0.14,0.16,"#33404e");
    box3(0.4,1.62,3.02,16.3,0.14,0.16,"#33404e");
    box3(bx-0.2,0.26,3.2,0.4,1.56,0.2,"#b8742c");
    box3(bx-0.14,0.86,3.06,0.28,0.34,0.14,"#8a5e0e");
    dq(bx+1.02+3.1,c2=>seg(c2,P(bx,1.02,3.06),P(bx,1.02,hz+0.28),"#9aa7b5",1.4));
    box3(bx-0.07,0.95,hz+0.16,0.14,0.14,0.12,"#5d6c7c");
    if(load)cyl3(bx,1.02,hz-0.36,0.3,0.5,"#6f7d8c");
    if(!(ph>=0.02&&ph<0.5))cyl3(2.6,1.22,0,0.3,0.5,"#6f7d8c");
    if(ph>=0.58)cyl3(13.4,1.22,0,0.3,0.5,"#7d8b9a");
    cyl3(3.25,1.28,0,0.3,0.5,"#7d8b9a");
    tag3(bx,1.0,3.7,"CR-01","천장크레인 5t","#f0a14c",2);
  })();
}

/* ============================================================
   씬 7종 — 실측 비율(1u=1m) 산업 라인
   ============================================================ */
function ramp(v,target,acc,dt){
  if(v<target)return Math.min(target,v+acc*dt);
  return Math.max(target,v-acc*dt);
}
const PARTC=["#3b82f6","#7c5cff","#d29922","#3fa86b"];

const SCENES={
/* ---- 1. 벨트컨베이어 (모터 기동/정지) ---- */
conveyor:{
 label:"포장 라인 1호기 — 벨트컨베이어 CV-101 (작업높이 0.75m)",
 wiresOut:[["MOTOR",[[14.72,5.0],[13.4,4.2],[12.45,2.75]]]],
 init:()=>({belt:0,spd:0,parts:[],count:0,spawn:0}),
 tick(st,o,dt){
   const macc=((cur.devCfg["M-101"]||{}).acc)||1.4;
   st.spd=ramp(st.spd,o.MOTOR?0.95*(cur.speedF||1):0,macc,dt);
   st.belt=(st.belt+st.spd*dt)%0.55;
   st.spawn-=dt;
   const clearIn=!st.parts.some(p=>!p.fall&&p.x<3.3);
   if(st.spd>0.3&&st.spawn<=0&&st.parts.length<7&&clearIn){st.parts.push({x:2.45,z:0.75,fall:0});st.spawn=1.7/(cur.speedF||1);}
   for(const p of st.parts){
     if(!p.fall){p.x+=st.spd*dt;if(p.x>11.65)p.fall=1;}
     else{p.z-=dt*1.8;p.x+=dt*0.25;if(p.z<=0.18){p.fall=2;st.count++;}}
   }
   st.parts=st.parts.filter(p=>p.fall<2);
 },
 draw(ctx,st,val,t){
   beltUnit(2,2.0,10,st.belt,st.spd>0.02,0.75);
   sh(0.9,1.7,1.3,1.2,0.25);
   box3(1.0,1.75,0,0.16,0.16,1.55,"#39434f");box3(2.0,1.75,0,0.16,0.16,1.55,"#39434f");
   box3(1.06,2.5,0,0.16,0.16,1.55,"#39434f");box3(2.0,2.5,0,0.16,0.16,1.55,"#39434f");
   box3(0.9,1.65,1.55,1.4,1.1,0.8,"#37424f");
   tag3(1.6,2.1,2.5,"HP-101","공급 호퍼","#8b98a8",2);
   st.parts.forEach((p,i)=>{
     if(!p.fall)sh(p.x-0.16,2.12,0.32,0.32,0.16);
     box3(p.x-0.16,2.12,p.z,0.32,0.34,0.3,PARTC[i%4]);
   });
   sh(11.85,1.8,1.05,1.0,0.25);
   box3(11.9,1.85,0,1.0,0.95,0.5,"#54442a");
   box3(11.96,1.91,0.4,0.88,0.06,0.1,"#54442a");box3(11.96,2.68,0.4,0.88,0.06,0.1,"#54442a");
   box3(12.1,2.66,0.5,0.4,0.28,0.26,"#44528a");
   tag3(12.3,2.8,0.95,"M-101","3.7kW 기어드모터","#8ec9ff");
   stackLight(12.85,1.6,!val("MOTOR"),false,val("MOTOR"));
   ledBoard(5.8,1.1,"생산수량 EA",String(st.count).padStart(4,"0"));
   tag3(7,2.3,0.95,"CV-101","벨트 0.6m × 10m","#8b98a8",2);
 }},

/* ---- 2. 이송 대차 (정역 인터록) ---- */
shuttle:{
 label:"자재 이송 대차 SH-201 — 정·역 인터록 (Z3: 동시출력 UNSAT)",
 wiresOut:[["MOTOR_FWD",[[14.72,5.0],[13.8,4.4],[13.6,3.7]]],
           ["MOTOR_REV",[[14.72,5.07],[15.6,4.5],[15.6,1.5],[1.6,1.5],[1.3,2.7]]]],
 init:()=>({pos:7,spd:0,carry:false,anim:0,count:0,stackN:0}),
 tick(st,o,dt){
   const tgt=o.MOTOR_FWD?1.1:o.MOTOR_REV?-1.1:0;
   st.spd=ramp(st.spd,tgt,2.2,dt);
   st.pos=Math.max(2.0,Math.min(12.5,st.pos+st.spd*dt));
   if(st.anim>0){st.anim-=dt;if(st.anim<=0){
     if(!st.carry){st.carry=true;}
     else{st.carry=false;st.count++;st.stackN=(st.stackN+1)%7;}
   }}
   else if(!st.carry&&st.pos<=2.05&&Math.abs(st.spd)<0.05)st.anim=0.7;
   else if(st.carry&&st.pos>=12.45&&Math.abs(st.spd)<0.05)st.anim=0.7;
 },
 draw(ctx,st,val,t){
   for(let x=2;x<=12.8;x+=0.85)box3(x,2.86,0,0.5,0.74,0.05,"#2a323c");
   box3(1.9,2.9,0.05,11.4,0.07,0.09,"#566472");
   box3(1.9,3.5,0.05,11.4,0.07,0.09,"#566472");
   sh(0.5,2.55,1.4,1.5,0.25);
   box3(0.55,2.6,0,1.3,1.4,0.55,"#37424f");
   if(!st.carry||st.pos>3)box3(0.75,2.85,0.55,0.8,0.85,0.6,"#7a5c2e");
   tag3(1.2,3.3,1.35,"DK-201","공급 도크","#8b98a8",2);
   sh(13.4,2.55,1.5,1.5,0.25);
   box3(13.45,2.6,0,1.4,1.4,0.55,"#37424f");
   for(let i=0;i<st.stackN;i++)
     box3(13.6+(i%2)*0.62,2.75+((i/2|0)%2)*0.62,0.55+(i/4|0)*0.45,0.55,0.55,0.42,"#7a5c2e");
   tag3(14.1,3.3,1.8,"DK-202","출하 도크","#8b98a8",2);
   box3(0.9,3.75,0,0.45,0.45,0.5,"#44528a");
   tag3(1.1,4.0,0.9,"M-202","역방향 윈치","#b9a3ff");
   box3(13.5,3.75,0,0.45,0.45,0.5,"#44528a");
   tag3(13.7,4.0,0.9,"M-201","정방향 윈치","#8ec9ff");
   const fwd=val("MOTOR_FWD"),rev=val("MOTOR_REV");
   sh(st.pos-0.78,2.7,1.56,1.1,0.28);
   box3(st.pos-0.75,2.75,0.14,1.5,1.0,0.42,fwd?"#2c5dad":rev?"#5d44c8":"#3a4656");
   if(st.carry||st.anim>0)box3(st.pos-0.45,2.85,0.56,0.85,0.8,0.6,"#7a5c2e");
   dq(st.pos+3.4+2,c2=>lamp(c2,P(st.pos,3.25,0.95),3,fwd?"#58a6ff":rev?"#9b7bff":"#27313c",fwd||rev));
   tag3(st.pos,3.0,1.15,"SH-201","이송 대차 2t","#dce4f0");
   stackLight(12.9,4.3,!fwd&&!rev,false,fwd||rev);
   ledBoard(6.2,1.3,"운반횟수",String(st.count).padStart(4,"0"));
 }},

/* ---- 3. 자동 세차 터널 ---- */
carwash:{
 label:"세차 터널 — 비누 → 헹굼 → 건조 (차량 4.3m 실측 비율)",
 wiresOut:[["SOAP",[[14.72,4.95],[5.1,4.6],[5.1,3.95]]],
           ["RINSE",[[14.72,5.0],[8.1,4.75],[8.1,3.95]]],
           ["DRY",[[14.72,5.05],[11.1,4.9],[11.1,3.95]]]],
 init:()=>({carX:-1.5,exiting:false,parts:[],count:0,col:0}),
 tick(st,o,dt){
   let tgt;
   if(o.SOAP){tgt=5;st.exiting=true;}
   else if(o.RINSE)tgt=8;
   else if(o.DRY)tgt=11;
   else if(st.exiting){tgt=21;if(st.carX>20){st.carX=-4;st.exiting=false;st.count++;st.col=(st.col+1)%3;}}
   else tgt=-1.5;
   const d=tgt-st.carX;
   st.carX+=Math.sign(d)*Math.min(Math.abs(d),dt*2.0);
   const sp=(x,kind)=>{for(let i=0;i<2;i++)st.parts.push({
     x:x+(Math.random()-0.5)*1.6,y:2.1+Math.random()*1.3,
     z:kind==="drop"?2.3:kind==="wind"?0.8+Math.random()*1.0:0.5+Math.random()*1.4,
     k:kind,life:1});};
   if(o.SOAP)sp(5,"foam"); if(o.RINSE)sp(8,"drop"); if(o.DRY)sp(11,"wind");
   st.parts.forEach(p=>{
     p.life-=dt*(p.k==="drop"?2.6:1.7);
     if(p.k==="foam")p.z+=dt*0.4;
     if(p.k==="drop")p.z-=dt*3.4;
     if(p.k==="wind")p.x+=dt*3.6;
   });
   st.parts=st.parts.filter(p=>p.life>0&&p.z>0).slice(-100);
 },
 draw(ctx,st,val,t){
   face(ctx,[P(0.4,1.9,0.012),P(17.6,1.9,0.012),P(17.6,4.0,0.012),P(0.4,4.0,0.012)],"#1a2026");
   box3(0.4,1.95,0,17.2,0.06,0.08,"#3c4854");
   box3(0.4,3.9,0,17.2,0.06,0.08,"#3c4854");
   const arch=(x,c,on,name,tg)=>{
     sh(x-0.2,1.6,0.45,2.5,0.22);
     box3(x-0.14,1.62,0,0.28,0.28,2.45,on?shade(c,0.8):"#2b333d");
     box3(x-0.14,3.62,0,0.28,0.28,2.45,on?shade(c,0.8):"#2b333d");
     box3(x-0.2,1.62,2.45,0.4,2.28,0.3,on?c:"#2c3743");
     tag3(x,1.62,3.1,tg,name,on?c:"#5d6c7c");
     if(on)dq(x+3.8+3,c2=>lamp(c2,P(x,2.7,2.42),3.5,c,true));
   };
   arch(5,"#58a6ff",val("SOAP"),"비누 분사 밸브","V-301");
   arch(8,"#7c5cff",val("RINSE"),"헹굼 펌프","P-301");
   arch(11,"#d9a514",val("DRY"),"건조 블로워","FN-301");
   const drawCar=(cx,col)=>{
     if(cx<-3.6||cx>19.5)return;
     const c=["#a83248","#3563a8","#6f7780"][col];
     sh(cx-2.1,2.1,4.2,1.75,0.3);
     box3(cx-2.15,2.12,0.32,4.3,1.7,0.6,c);
     box3(cx-0.95,2.22,0.92,2.05,1.5,0.55,"#1d2a3a");
     box3(cx-1.6,2.0,0,0.6,0.22,0.55,"#11161d");box3(cx+1.0,2.0,0,0.6,0.22,0.55,"#11161d");
     box3(cx-1.6,3.7,0,0.6,0.22,0.55,"#11161d");box3(cx+1.0,3.7,0,0.6,0.22,0.55,"#11161d");
   };
   drawCar(st.carX,st.col);
   if(st.exiting||st.carX>-1.4)drawCar(-2.8,(st.col+1)%3);
   st.parts.forEach(p=>{
     const q=P(p.x,p.y,p.z),a=Math.max(0,Math.min(1,p.life));
     dq(99,c2=>{
       if(p.k==="foam"){c2.beginPath();c2.arc(q[0],q[1],2.4,0,7);c2.fillStyle=`rgba(170,210,255,${(a*0.8).toFixed(2)})`;c2.fill();}
       else if(p.k==="drop")seg(c2,q,[q[0],q[1]+6],`rgba(88,166,255,${a.toFixed(2)})`,1.4);
       else seg(c2,q,[q[0]+9,q[1]-3],`rgba(217,165,20,${(a*0.8).toFixed(2)})`,1.4);
     });
   });
   ledBoard(2.2,1.15,"세차완료",String(st.count).padStart(4,"0"));
 }},

/* ---- 4. 부품 카운터 + 배출 (CTU) ---- */
counter:{
 label:"검수 라인 — 광전센서 카운트, 10개 도달 시 배출 (CTU C1)",
 wiresIn:[["PART_SENSOR",[[9.25,2.75],[9.25,4.45],[14.68,5.1]]]],
 wiresOut:[["EJECT",[[14.72,4.95],[10.75,4.6],[10.75,2.1],[10.75,1.85]]]],
 init:()=>({belt:0,parts:[],spawn:0.4,blocked:false,good:0,ejected:0,rod:0}),
 sense(st,plc){plc.set("PART_SENSOR",st.blocked);},
 tick(st,o,dt){
   st.belt=(st.belt+1.1*(cur.speedF||1)*dt)%0.55;
   st.spawn-=dt;
   if(st.spawn<=0&&st.parts.length<9){st.parts.push({x:2.4,y:2.2,z:0.75,st:0});st.spawn=1.2/(cur.speedF||1);}
   st.rod=ramp(st.rod,o.EJECT?1:0,4,dt);
   st.blocked=false;
   st.parts.sort((a,b)=>b.x-a.x);
   let prevX=99;
   for(const p of st.parts){
     if(p.st===0){
       let mv=1.1*(cur.speedF||1)*dt;
       if(p.x+mv>prevX-0.4)mv=Math.max(0,prevX-0.4-p.x);
       p.x+=mv;prevX=p.x;
       if(Math.abs(p.x-9.2)<0.17)st.blocked=true;
       if(p.x>10.45&&p.x<10.95&&st.rod>0.6)p.st=1;
       if(p.x>12.6)p.st=2;
       continue;
     }
     if(p.st===1){
       p.y+=dt*2.2;
       if(p.y>3.4){p.st=9;st.ejected++;}
     }else if(p.st===2){
       p.z-=dt*1.8;p.x+=dt*0.2;
       if(p.z<0.2){p.st=9;st.good++;}
     }
   }
   st.parts=st.parts.filter(p=>p.st!==9);
 },
 draw(ctx,st,val,t){
   beltUnit(2,2.0,11,st.belt,true,0.75);
   box3(9.16,1.84,0,0.05,0.05,1.0,"#222a34");
   box3(9.16,2.74,0,0.05,0.05,1.0,"#222a34");
   box3(9.13,2.72,0.86,0.11,0.09,0.1,"#1a212b");
   dq(9.2+2.3+1.5,c2=>{
     const a=P(9.19,1.89,0.92),b=P(9.19,2.74,0.92);
     c2.save();
     if(st.blocked){c2.shadowColor="#ff5b5b";c2.shadowBlur=8;}
     seg(c2,a,b,st.blocked?"#ff5b5b":"rgba(255,91,91,.32)",st.blocked?2:1);
     c2.restore();
   });
   tag3(9.19,2.74,1.05,"SN-101","광전센서 50mm","#ff8f8f");
   sh(10.4,1.4,0.6,0.45,0.22);
   box3(10.42,1.42,0.6,0.56,0.4,0.32,"#37424f");
   if(st.rod>0.02)box3(10.62,1.82,0.66,0.16,st.rod*0.85,0.16,"#aab6c4");
   tag3(10.7,1.6,1.1,"CY-101","배출 실린더","#f5b14c");
   box3(10.3,2.66,0.42,0.85,0.85,0.07,"#33404d");
   sh(10.3,3.55,0.8,0.8,0.24);
   box3(10.32,3.56,0,0.78,0.78,0.5,"#6e532a");
   tag3(10.7,3.95,0.95,"NG-BOX",`배출 ${st.ejected}`,"#f5b14c");
   st.parts.forEach((p,i)=>{
     if(p.st===0)sh(p.x-0.13,p.y-0.08,0.26,0.26,0.14);
     box3(p.x-0.13,p.y-0.13,p.z,0.26,0.26,0.24,PARTC[i%4]);
   });
   sh(12.9,1.85,0.95,0.9,0.24);
   box3(12.95,1.9,0,0.9,0.85,0.5,"#54442a");
   const c1=cur.plc.counters.C1;
   ledBoard(5.4,1.15,"C1 카운트",`${String(c1?c1.cnt:0).padStart(2,"0")} / ${c1?c1.preset:10}`,c1&&c1.q?"#f5b14c":"#7ee787");
   ledBoard(13.6,1.2,"양품 EA",String(st.good).padStart(4,"0"));
 }},

/* ---- 5. 로봇 용접 셀 ---- */
weld:{
 label:"로봇 용접 셀 RB-401 — 3×4m 셀 · 안전펜스 1.4m (ISO 13857)",
 wiresOut:[["CLAMP",[[14.72,4.95],[8.3,4.85],[7.6,3.0]]],
           ["WELD",[[14.72,5.0],[10.2,5.0],[6.4,3.4]]],
           ["UNCLAMP",[[14.72,5.05],[8.6,4.95],[7.9,3.0]]]],
 init:()=>({phase:"idle",partX:1.6,partOn:false,arm:0,clamp:0,sparks:[],count:0,weaveT:0}),
 tick(st,o,dt){
   st.clamp=ramp(st.clamp,(o.CLAMP||o.WELD)?1:0,2.5,dt);
   const rspd=((cur.devCfg["RB-401"]||{}).spd||100)/100;
   st.arm=ramp(st.arm,o.WELD?1:0,2.2*rspd,dt);
   const cycle=o.CLAMP||o.WELD||o.UNCLAMP;
   if(!st.partOn&&!cycle){
     st.partX=Math.min(7.55,st.partX+dt*1.1);
     if(st.partX>=7.54)st.partOn=true;
   }
   if(st.partOn)st.wasCycle=st.wasCycle||cycle;
   if(st.partOn&&st.wasCycle&&!cycle){
     st.partOn=false;st.wasCycle=false;st.out=7.55;
   }
   if(st.out!==undefined){
     st.out+=dt*1.1;
     if(st.out>12.9){st.out=undefined;st.count++;st.partX=1.6;}
   }
   if(o.WELD){st.weaveT+=dt;
     const rc=cur.devCfg["RB-401"]||{};
     const ro=rc.off||[0,0,0];
     const tip=P(7.55+ro[0]+Math.sin(st.weaveT*9)*0.07,2.28+ro[1],1.02+ro[2]);
     for(let i=0;i<6;i++)st.sparks.push({x:tip[0],y:tip[1],vx:(Math.random()-0.5)*150,vy:-Math.random()*110,life:0.4+Math.random()*0.5});
   }
   st.sparks.forEach(p=>{p.life-=dt;p.x+=p.vx*dt;p.y+=p.vy*dt;p.vy+=220*dt;});
   st.sparks=st.sparks.filter(p=>p.life>0).slice(-200);
 },
 draw(ctx,st,val,t){
   fence(5.0,1.2,9.7,4.5,"front");
   beltUnit(1.2,2.05,3.6,(t*0.5)%0.55,true,0.75);
   beltUnit(9.9,2.05,3.4,(t*0.5)%0.55,true,0.75);
   sh(7.2,1.9,0.8,0.8,0.26);
   box3(7.25,1.95,0,0.66,0.66,0.78,"#3a4654");
   tag3(7.58,2.0,1.0,"WT-401","용접 지그","#8b98a8",2);
   beltUnit(5.35,2.05,1.7,(t*0.5)%0.55,true,0.75);
   beltUnit(8.0,2.05,1.55,(t*0.5)%0.55,true,0.75);
   const px=st.out!==undefined?st.out:st.partX;
   if(st.out!==undefined||st.partX>1.55){
     const pz=(px>7.2&&px<8.0)?0.79:0.76;
     box3(px-0.3,2.13,pz,0.6,0.42,0.13,"#7e8894");
   }
   const cg=st.clamp;
   box3(7.18,1.88+cg*0.16,0.78,0.18,0.16,0.3,"#b8742c");
   box3(7.18,2.62-cg*0.16,0.78,0.18,0.16,0.3,"#b8742c");
   tag3(7.27,2.7,1.25,"CL-401","공압 클램프",val("CLAMP")||val("WELD")?"#f5b14c":"#5d6c7c");
   sh(5.95,2.6,0.75,0.7,0.3);
   cyl3(6.3,2.95,0,0.27,0.3,"#caa011");
   cyl3(6.3,2.95,0.3,0.18,0.35,"#d9a514");
   dq(6.3+2.95+1.4,c2=>{
     const a0=st.arm,a=a0*a0*(3-2*a0);
     const S=P(6.3,2.95,0.66);
     const wv=val("WELD")?Math.sin(st.weaveT*9)*0.07:0;
     const rc2=cur.devCfg["RB-401"]||{};
     const ro2=rc2.off||[0,0,0];
     const T=a<0.02?P(6.85,2.95,2.0)
       :P(6.85+((7.55+ro2[0]+wv)-6.85)*a,2.95+((2.3+ro2[1])-2.95)*a,2.0+((1.04+ro2[2])-2.0)*a);
     const E=[(S[0]+T[0])/2+0.15*view.s*0.04,Math.min(S[1],T[1])-0.62*view.s*0.8*0.55];
     c2.lineCap="round";
     c2.strokeStyle="#8a6d10";c2.lineWidth=0.2*view.s+2;
     c2.beginPath();c2.moveTo(S[0],S[1]);c2.lineTo(E[0],E[1]);c2.lineTo(T[0],T[1]);c2.stroke();
     c2.strokeStyle="#e0a418";c2.lineWidth=0.2*view.s;
     c2.beginPath();c2.moveTo(S[0],S[1]);c2.lineTo(E[0],E[1]);c2.lineTo(T[0],T[1]);c2.stroke();
     for(const j of[S,E])
       {c2.beginPath();c2.arc(j[0],j[1],0.11*view.s,0,7);c2.fillStyle="#5c4a0e";c2.fill();}
     c2.strokeStyle="#39434f";c2.lineWidth=0.07*view.s;
     c2.beginPath();c2.moveTo(T[0],T[1]);c2.lineTo(T[0]+4,T[1]+0.16*view.s);c2.stroke();
     if(val("WELD")){
       const f=0.6+Math.random()*0.4;
       c2.save();c2.shadowColor="#bfe3ff";c2.shadowBlur=22*f;
       c2.beginPath();c2.arc(T[0]+4,T[1]+0.16*view.s,3.2*f,0,7);
       c2.fillStyle="rgba(225,243,255,"+(0.85*f).toFixed(2)+")";c2.fill();c2.restore();
     }
   });
   tag3(6.3,2.95,1.55,"RB-401","6축 용접로봇",val("WELD")?"#ffd76b":"#caa011");
   dq(99,c2=>{
     for(const p of st.sparks){
       const a=Math.max(0,p.life*1.8);
       seg(c2,[p.x,p.y],[p.x-p.vx*0.02,p.y-p.vy*0.02],`rgba(255,${200+Math.random()*55|0},107,${Math.min(1,a).toFixed(2)})`,1.3);
     }
   });
   stackLight(9.4,4.85,!val("CLAMP")&&!val("WELD")&&!val("UNCLAMP"),val("UNCLAMP"),val("WELD")||val("CLAMP"));
   ledBoard(3.0,1.0,"용접완료",String(st.count).padStart(4,"0"));
 }},

/* ---- 6. 배치 탱크 (충전→교반→배출) ---- */
batch:{
 label:"배치 플랜트 TK-501 — 충전 8s → 교반 10s → 배출 6s",
 wiresOut:[["FILL_VALVE",[[14.72,4.95],[4.6,4.9],[4.5,3.2]]],
           ["MIXER",[[14.72,5.0],[6.2,5.0],[6.0,3.6]]],
           ["DRAIN_VALVE",[[14.72,5.05],[8.7,5.0],[8.7,3.6]]]],
 init:()=>({level:0,mix:0,drum:0,count:0,drumX:8.75,puffT:0,puffs:[]}),
 tick(st,o,dt){
   if(o.FILL_VALVE)st.level=Math.min(1,st.level+dt/8);
   if(o.DRAIN_VALVE){const d=Math.min(st.level,dt/6);st.level-=d;st.drum=Math.min(1,st.drum+d*1.1);}
   if(o.MIXER)st.mix+=dt*5;
   if(st.wasDrain&&!o.DRAIN_VALVE&&st.drum>0.2){st.exit=true;}
   st.wasDrain=o.DRAIN_VALVE;
   if(st.exit){st.drumX+=dt*1.4;
     if(st.drumX>16.5){st.exit=false;st.drumX=8.75;st.drum=0;st.count++;}}
   if(o.MIXER){st.puffT-=dt;
     if(st.puffT<=0){st.puffs.push({x:5.7+Math.random()*0.7,y:2.6,z:3.25,life:1});st.puffT=0.25;}}
   st.puffs.forEach(p=>{p.life-=dt*0.9;p.z+=dt*0.5;});
   st.puffs=st.puffs.filter(p=>p.life>0);
 },
 draw(ctx,st,val,t){
   sh(4.9,1.7,2.3,2.0,0.3);
   for(const[lx,ly]of[[5.2,2.0],[6.9,2.0],[5.2,3.3],[6.9,3.3]])box3(lx-0.07,ly-0.07,0,0.14,0.14,0.55,"#39434f");
   cyl3(6.05,2.66,0.55,1.05,2.1,"#46535f");
   box3(5.78,2.4,2.66,0.5,0.45,0.42,"#44528a");
   tag3(6.0,2.6,3.35,"AG-501","교반 모터 11kW",val("MIXER")?"#8ec9ff":"#5d6c7c");
   dq(2+2.6+3.5,c2=>{
     const a=P(1.4,2.6,3.3),b=P(6.05,2.6,3.3),c=P(6.05,2.6,2.85);
     seg(c2,a,b,"#566472",3);seg(c2,b,c,"#566472",3);
     if(val("FILL_VALVE")){
       c2.save();c2.strokeStyle="#58c4ff";c2.lineWidth=2;c2.shadowColor="#58c4ff";c2.shadowBlur=7;
       c2.setLineDash([5,7]);c2.lineDashOffset=-(t*40)%12;
       c2.beginPath();c2.moveTo(a[0],a[1]);c2.lineTo(b[0],b[1]);c2.lineTo(c[0],c[1]);c2.stroke();c2.restore();
     }
   });
   box3(4.35,2.46,3.12,0.3,0.28,0.34,val("FILL_VALVE")?"#2b86c8":"#3a4654");
   tag3(4.5,2.6,3.7,"V-501","충전 밸브",val("FILL_VALVE")?"#58c4ff":"#5d6c7c");
   dq(7.2+3.4+1,c2=>{
     const g0=P(7.15,3.42,0.62),g1=P(7.15,3.42,2.55);
     seg(c2,g0,g1,"#2b333d",4);
     const lv=P(7.15,3.42,0.62+st.level*1.86);
     seg(c2,g0,lv,val("MIXER")?"#7cc4ff":"#58a6ff",3);
     txt(c2,[g1[0]+10,g1[1]],Math.round(st.level*100)+"%","#8ec9ff",10,"left");
   });
   tag3(6.05,2.66,2.8,"TK-501","배치 탱크 2㎘","#9fb3c8");
   dq(7.6+3.2+1.2,c2=>{
     const a=P(7.05,3.2,0.5),b=P(8.75,3.45,0.5),c=P(8.75,3.45,0.95);
     seg(c2,a,b,"#566472",3);
     if(val("DRAIN_VALVE")){
       c2.save();c2.strokeStyle="#9be58e";c2.lineWidth=2;c2.shadowColor="#9be58e";c2.shadowBlur=7;
       c2.setLineDash([5,7]);c2.lineDashOffset=-(t*40)%12;
       c2.beginPath();c2.moveTo(a[0],a[1]);c2.lineTo(b[0],b[1]);c2.stroke();c2.restore();
     }
   });
   box3(7.85,3.18,0.4,0.3,0.28,0.32,val("DRAIN_VALVE")?"#3f9d52":"#3a4654");
   tag3(8.0,3.3,1.0,"V-502","배출 밸브",val("DRAIN_VALVE")?"#9be58e":"#5d6c7c");
   sh(st.drumX-0.45,3.0,0.95,0.9,0.26);
   cyl3(st.drumX,3.45,0,0.4,0.92,"#2e5e8e");
   dq(st.drumX+3.45+1.5,c2=>{
     const p=P(st.drumX,3.45,0.96);
     txt(c2,[p[0],p[1]],Math.round(st.drum*100)+"%","#9fc8e8",9);
   });
   tag3(st.drumX,3.45,1.1,"DR-501",`제품 드럼`,"#8ec9ff");
   st.puffs.forEach(p=>{
     const q=P(p.x,p.y,p.z);
     dq(99,c2=>{c2.beginPath();c2.arc(q[0],q[1],4+(1-p.life)*7,0,7);
       c2.fillStyle=`rgba(190,205,220,${(p.life*0.25).toFixed(2)})`;c2.fill();});
   });
   stackLight(9.9,2.2,st.level<0.02&&!val("FILL_VALVE"),val("DRAIN_VALVE"),val("FILL_VALVE")||val("MIXER"));
   ledBoard(2.2,1.0,"배치 완료",String(st.count).padStart(3,"0"));
 }},

/* ---- 비전 검사·분기 라인 ---- */
vision:{
 label:"비전 검사·분기 라인 VS-701 — 카메라 판정 → 게이트 A(양품)/B(불량)",
 speedCtl:true, ngCtl:true,
 wiresIn:[["SEL_A",[[8.6,2.85],[8.6,4.5],[14.66,5.15]]],
          ["SEL_B",[[8.75,2.9],[8.95,4.6],[14.7,5.2]]]],
 wiresOut:[["GATE_A",[[14.72,4.95],[11.5,4.55],[10.55,2.9]]],
           ["GATE_B",[[14.72,5.0],[11.0,4.65],[10.4,3.0]]]],
 init:()=>({belt:0,parts:[],spawn:0.6,ok:0,ng:0,insp:0,flash:0,sel:0,selT:0,clearSel:false,armA:0,armB:0,verdicts:[],lastNG:false}),
 sense(st,plc){
   if(st.clearSel){plc.set("SEL_A",false);plc.set("SEL_B",false);st.clearSel=false;}
   if(st.sel>0){plc.set("SEL_A",true);plc.set("SEL_B",false);}
   else if(st.sel<0){plc.set("SEL_B",true);plc.set("SEL_A",false);}
 },
 tick(st,o,dt){
   const F=cur.speedF||1, v=1.0*F;
   st.belt=(st.belt+v*dt)%0.55;
   st.spawn-=dt;
   if(st.spawn<=0&&st.parts.length<10){
     st.parts.push({x:2.4,z:0.75,y:2.31,ng:Math.random()*100<(cur.ngRate??8),insp:false,st:0});
     st.spawn=2.0/F;
   }
   st.flash=Math.max(0,st.flash-dt*2.5);
   if(st.sel!==0){st.selT-=dt;if(st.selT<=0){st.sel=0;st.clearSel=true;}}
   st.armA=ramp(st.armA,o.GATE_A?1:0,4,dt);
   st.armB=ramp(st.armB,o.GATE_B?1:0,4,dt);
   st.parts.sort((a,b)=>b.x-a.x);
   let prevX=99;
   for(const p of st.parts){
     if(p.st===0){
       let move=v*dt;
       const gateIdle=st.armA<0.5&&st.armB<0.5;
       if(gateIdle&&p.x+move>10.2)move=Math.max(0,10.2-p.x);
       if(p.x+move>prevX-0.42)move=Math.max(0,prevX-0.42-p.x);
       p.x+=move; prevX=p.x;
       if(!p.insp&&p.x>=8.55){
         p.insp=true;
         if(cur.faults.camOff){
           st.lastShot={off:true};
         }else{
           st.insp++;st.flash=1;st.lastNG=p.ng;
           const det=p.ng?(Math.random()<visionOptics(cur).conf):true;
           const judgedNG=p.ng&&det;
           if(p.ng&&!det)logEv("warn","VS-701 미검출 — 조도/분해능 부족(NG 통과)");
           st.sel=judgedNG?-1:1;st.selT=0.35;
           st.verdicts.push({x:p.x,ng:p.ng,life:1});
           st.lastShot={ng:p.ng,dx:0.25+Math.random()*0.5,dy:0.25+Math.random()*0.5,
             ms:(8+Math.random()*9)|0,n:st.insp};
           if(p.ng)logEv("warn","VS-701 NG 판정 — 게이트 B 분기 지시");
         }
       }
       if(p.x>=10.35&&p.x<10.8&&st.armB>0.5&&p.ng)p.st=1;
       if(p.x>12.9)p.st=2;
     }else if(p.st===1){
       p.y+=dt*2.0;
       if(p.y>3.35){p.st=9;st.ng++;}
     }else if(p.st===2){
       p.z-=dt*1.8;p.x+=dt*0.2;
       if(p.z<0.2){p.st=9;st.ok++;
         if(p.ng){st.leak=(st.leak||0)+1;logEv("warn","⚠ 불량 유출 — 미검사/미분기 NG가 양품 적재됨");}}
     }
   }
   st.parts=st.parts.filter(p=>p.st!==9);
   st.verdicts.forEach(vd=>vd.life-=dt*0.8);
   st.verdicts=st.verdicts.filter(vd=>vd.life>0).slice(-6);
 },
 draw(ctx,st,val,t){
   beltUnit(2,2.0,11,st.belt,true,0.75);
   box3(8.52,1.86,0,0.07,0.07,1.62,"#39434f");
   box3(8.52,2.7,0,0.07,0.07,1.62,"#39434f");
   box3(8.42,1.86,1.62,0.3,0.95,0.22,"#2c3743");
   box3(8.49,2.18,1.34,0.16,0.3,0.28,"#1a212b");
   dq(8.6+2.4+1.6,c2=>{
     const lens=P(8.57,2.33,1.32);
     c2.beginPath();c2.arc(lens[0],lens[1],2.6,0,7);
     c2.fillStyle=st.flash>0.4?"#cfe9ff":"#3a4a5c";c2.fill();
     if(st.flash>0.05){
       const a=P(8.57,1.95,1.3),b=P(8.57,2.75,1.3),c0=P(8.57,2.05,0.78),d0=P(8.57,2.66,0.78);
       c2.beginPath();c2.moveTo(a[0],a[1]);c2.lineTo(b[0],b[1]);c2.lineTo(d0[0],d0[1]);c2.lineTo(c0[0],c0[1]);c2.closePath();
       c2.fillStyle=`rgba(190,225,255,${(st.flash*0.3).toFixed(2)})`;c2.fill();
     }
     lamp(c2,P(8.57,2.74,1.55),2.8,st.lastNG?"#f85149":"#3fb950",st.flash>0.05);
   });
   tag3(8.57,2.7,1.95,"VS-701","비전 카메라 검사",st.flash>0.4?"#cfe9ff":"#8ec9ff");
   box3(10.42,1.8,0.62,0.14,0.14,0.4,"#39434f");
   dq(10.5+2.6+1.2,c2=>{
     const piv=P(10.5,1.92,0.92);
     const ang=st.armB*0.95;
     const tipW=P(10.5+Math.sin(ang)*0.75,1.92+Math.cos(ang)*0.75,0.92);
     c2.lineCap="round";
     c2.strokeStyle=st.armB>0.5?"#b86a2c":"#566472";c2.lineWidth=0.09*view.s;
     c2.beginPath();c2.moveTo(piv[0],piv[1]);c2.lineTo(tipW[0],tipW[1]);c2.stroke();
   });
   tag3(10.5,2.1,1.35,"DV-701","분기 게이트",val("GATE_B")?"#f5b14c":val("GATE_A")?"#7ee787":"#5d6c7c");
   box3(10.25,3.4,0,0.85,0.8,0.5,"#6e3a3a");
   tag3(10.65,3.8,0.95,"NG-BOX",`불량 ${st.ng}`,"#ff8f8f");
   sh(13.1,1.85,1.0,0.95,0.25);
   box3(13.15,1.9,0,0.95,0.9,0.5,"#3f5a3f");
   tag3(13.6,2.35,0.95,"OK-PLT",`양품 적재`,"#7ee787",2);
   st.parts.forEach((p,i)=>{
     if(p.st===0)sh(p.x-0.14,p.y-0.12,0.28,0.28,0.14);
     box3(p.x-0.14,p.y-0.14,p.z,0.28,0.28,0.26,p.ng?"#8a4040":PARTC[i%4]);
     if(p.ng)dq(p.x+p.y+1.2,c2=>{const q=P(p.x,p.y-0.02,p.z+0.27);
       c2.beginPath();c2.arc(q[0],q[1],1.6,0,7);c2.fillStyle="#321";c2.fill();});
   });
   st.verdicts.forEach(vd=>{
     dq(99,c2=>{
       const q=P(vd.x,1.7,1.4+(1-vd.life)*0.5);
       c2.font="700 11px ui-monospace";c2.textAlign="center";
       c2.fillStyle=vd.ng?`rgba(248,81,73,${vd.life.toFixed(2)})`:`rgba(63,185,80,${vd.life.toFixed(2)})`;
       c2.fillText(vd.ng?"NG":"OK",q[0],q[1]);
     });
   });
   dq(999,c2=>{
     const mw=204,mh=128,mx=view.W-mw-12,my=92;
     c2.fillStyle="rgba(8,12,18,.92)";c2.strokeStyle="#2b3743";c2.lineWidth=1;
     c2.beginPath();c2.roundRect(mx,my,mw,mh,6);c2.fill();c2.stroke();
     c2.font="9.5px ui-monospace,monospace";c2.textAlign="left";c2.fillStyle="#5d6c7c";
     c2.fillText("VS-701 검사 모니터 · 640×480 · ROI 3",mx+8,my+14);
     const so=st.lastShot;
     if(cur.faults.camOff){
       c2.fillStyle="#f85149";c2.font="700 12px ui-monospace";
       c2.fillText("카메라 오프라인",mx+8,my+44);
       c2.font="9.5px ui-monospace";c2.fillStyle="#8b98a8";
       c2.fillText("부품 미검사 통과 중 — 유출 위험",mx+8,my+62);
       return;
     }
     if(!so){c2.fillText("부품 대기 중…",mx+8,my+36);return;}
     const px0=mx+10,py0=my+24,pw=mw-92,ph=mh-36;
     c2.fillStyle="#1b232e";c2.fillRect(px0,py0,pw,ph);
     c2.strokeStyle="#3a4756";c2.strokeRect(px0,py0,pw,ph);
     c2.fillStyle="#2c3845";c2.fillRect(px0+14,py0+12,pw-28,ph-24);
     c2.setLineDash([3,3]);c2.strokeStyle="#3fb950";
     c2.strokeRect(px0+10,py0+8,pw-20,ph-16);
     c2.strokeRect(px0+18,py0+16,26,18);
     c2.strokeRect(px0+pw-46,py0+ph-36,28,20);
     c2.setLineDash([]);
     c2.strokeStyle="rgba(88,166,255,.35)";
     c2.beginPath();c2.moveTo(px0+pw/2,py0);c2.lineTo(px0+pw/2,py0+ph);
     c2.moveTo(px0,py0+ph/2);c2.lineTo(px0+pw,py0+ph/2);c2.stroke();
     if(so.ng){
       c2.fillStyle="#7a2e2e";c2.beginPath();
       c2.arc(px0+14+so.dx*(pw-28),py0+12+so.dy*(ph-24),4.5,0,7);c2.fill();
       c2.strokeStyle="#f85149";c2.lineWidth=1.4;
       c2.strokeRect(px0+14+so.dx*(pw-28)-8,py0+12+so.dy*(ph-24)-8,16,16);
     }
     const ix=mx+pw+20;
     c2.font="700 15px ui-monospace";c2.fillStyle=so.ng?"#f85149":"#3fb950";
     c2.fillText(so.ng?"NG":"OK",ix,py0+16);
     c2.font="9px ui-monospace";c2.fillStyle="#7f8a9a";
     c2.fillText("표면: "+(so.ng?"결함":"양호"),ix,py0+34);
     c2.fillText("치수: 합격",ix,py0+47);
     c2.fillText("처리: "+so.ms+" ms",ix,py0+60);
     c2.fillText("샷 #"+String(so.n).padStart(4,"0"),ix,py0+73);
     if((st.leak||0)>0){c2.fillStyle="#f0c26b";c2.fillText("유출 "+st.leak+"건!",ix,py0+88);}
     const op2=visionOptics(cur);
     c2.fillStyle="#5d6c7c";c2.textAlign="left";
     c2.fillText(`FOV ${op2.fovW.toFixed(0)}×${op2.fovH.toFixed(0)}mm · ${op2.res.toFixed(0)}µm/px · 신뢰도 ${(op2.conf*100).toFixed(0)}%`,mx+8,my+mh-6);
   });
   const tot=st.ok+st.ng;
   ledBoard(4.6,1.1,"불량율",tot?((st.ng/tot)*100).toFixed(1)+"%":"0.0%",st.ng/Math.max(1,tot)>0.12?"#f5b14c":"#7ee787");
   ledBoard(6.4,1.1,"검사수량",String(st.insp).padStart(4,"0"));
   stackLight(12.4,4.4,!val("GATE_A")&&!val("GATE_B"),val("GATE_B"),val("GATE_A"));
 }},

/* ---- 급수 펌프장 (리드/래그 병렬·페일오버) ---- */
pumps:{
 label:"급수 펌프장 P-801 — 병렬 2대 리드/래그 자동 교대 · 수위 폐루프",
 demandCtl:true,
 wiresIn:[["DEMAND",[[11.1,3.85],[11.1,4.6],[14.66,5.15]]],
          ["HIGH_DEMAND",[[11.45,3.95],[11.7,4.7],[14.7,5.2]]]],
 wiresOut:[["PUMP_LEAD",[[14.72,4.95],[6.2,4.75],[4.85,2.7]]],
           ["PUMP_LAG",[[14.72,5.0],[6.5,4.85],[4.85,3.85]]]],
 init:()=>({level:0.62,supplied:0,sd:0,sh:0}),
 sense(st,plc){
   if(st.level<0.55)st.sd=1; else if(st.level>0.68)st.sd=0;
   if(st.level<0.32)st.sh=1; else if(st.level>0.45)st.sh=0;
   plc.set("DEMAND",!!st.sd); plc.set("HIGH_DEMAND",!!st.sh);
 },
 tick(st,o,dt){
   const drain=0.048*(cur.demandF??1)*(st.level>0?1:0);
   let fill=0;
   if(o.PUMP_LEAD)fill+=0.055;
   if(o.PUMP_LAG)fill+=0.055;
   st.level=Math.max(0,Math.min(1,st.level+(fill-drain)*dt));
   st.supplied+=fill*dt*9;
 },
 draw(ctx,st,val,t){
   sh(1.3,2.0,2.3,2.0,0.25);
   box3(1.35,2.05,0,2.2,1.9,0.5,"#2b3743");
   dq(2.4+3+0.6,c2=>{
     face(c2,[P(1.5,2.2,0.46),P(3.4,2.2,0.46),P(3.4,3.8,0.46),P(1.5,3.8,0.46)],"rgba(46,94,142,.75)");
   });
   tag3(2.4,3.0,0.9,"RSV-801","원수조","#8ec9ff",2);
   const pump=(py,sym,tg,nm)=>{
     const on=val(sym);
     sh(4.4,py-0.35,1.1,0.8,0.24);
     box3(4.45,py-0.3,0,0.6,0.6,0.5,"#44528a");
     cyl3(5.3,py,0,0.26,0.45,on?"#3f6fae":"#3a4654");
     dq(5.3+py+0.8,c2=>lamp(c2,P(5.3,py,0.6),3,on?"#3fb950":"#27313c",on));
     tag3(4.9,py+0.15,0.95,tg,nm,on?"#7ee787":"#5d6c7c");
     dq(4+py+0.5,c2=>{
       const a=P(3.55,py,0.25),b=P(4.45,py,0.25);
       seg(c2,a,b,"#566472",3);
       if(on){c2.save();c2.strokeStyle="#58c4ff";c2.lineWidth=2;c2.shadowColor="#58c4ff";c2.shadowBlur=6;
         c2.setLineDash([5,7]);c2.lineDashOffset=-(t*40)%12;
         c2.beginPath();c2.moveTo(a[0],a[1]);c2.lineTo(b[0],b[1]);c2.stroke();c2.restore();}
     });
     dq(8+py+1.5,c2=>{
       const a=P(5.55,py,0.3),b=P(7.6,py,0.3),c0=P(7.6,3.1,2.7),d0=P(10.6,3.1,2.7);
       seg(c2,a,b,"#566472",3);seg(c2,b,c0,"#566472",3);seg(c2,c0,d0,"#566472",3);
       if(on){c2.save();c2.strokeStyle="#58c4ff";c2.lineWidth=2;c2.shadowColor="#58c4ff";c2.shadowBlur=6;
         c2.setLineDash([5,7]);c2.lineDashOffset=-(t*44)%12;
         c2.beginPath();c2.moveTo(a[0],a[1]);c2.lineTo(b[0],b[1]);c2.lineTo(c0[0],c0[1]);c2.lineTo(d0[0],d0[1]);c2.stroke();c2.restore();}
     });
   };
   pump(2.35,"PUMP_LEAD","P-801A","리드 펌프");
   pump(3.55,"PUMP_LAG","P-801B","래그 펌프");
   sh(10.3,2.0,2.5,2.2,0.3);
   for(const[lx,ly]of[[10.6,2.3],[12.4,2.3],[10.6,3.7],[12.4,3.7]])box3(lx-0.08,ly-0.08,0,0.16,0.16,0.55,"#39434f");
   cyl3(11.5,3.0,0.55,1.15,2.3,"#46535f");
   tag3(11.5,3.0,3.05,"TK-801","급수 탱크 5㎘","#9fb3c8");
   dq(12.7+3.2+1,c2=>{
     const g0=P(12.65,3.55,0.7),g1=P(12.65,3.55,2.7);
     seg(c2,g0,g1,"#2b333d",4);
     const lv=P(12.65,3.55,0.7+st.level*1.94);
     seg(c2,g0,lv,st.level<0.32?"#f85149":st.level<0.55?"#d9a514":"#58a6ff",3);
     const m55=P(12.65,3.55,0.7+0.55*1.94),m30=P(12.65,3.55,0.7+0.32*1.94);
     seg(c2,[m55[0]-5,m55[1]],[m55[0]+5,m55[1]],"#d9a514",1.5);
     seg(c2,[m30[0]-5,m30[1]],[m30[0]+5,m30[1]],"#f85149",1.5);
     txt(c2,[g1[0]+10,g1[1]+4],Math.round(st.level*100)+"%","#8ec9ff",10.5,"left",true);
   });
   dq(14+3+1,c2=>{
     const a=P(12.62,3.0,0.5),b=P(16.8,3.0,0.5);
     seg(c2,a,b,"#566472",3);
     if(st.level>0.01){c2.save();c2.strokeStyle="#9be58e";c2.lineWidth=1.8;
       c2.setLineDash([4,8]);c2.lineDashOffset=-(t*30*(cur.demandF??1))%12;
       c2.beginPath();c2.moveTo(a[0],a[1]);c2.lineTo(b[0],b[1]);c2.stroke();c2.restore();}
   });
   tag3(15.8,3.0,0.85,"공정 공급","수요 부하 "+Math.round((cur.demandF??1)*100)+"%","#9be58e",2);
   stackLight(9.0,2.0,st.level<0.15,val("PUMP_LAG"),val("PUMP_LEAD")||val("PUMP_LAG"));
   ledBoard(7.6,1.2,"누적 공급 ㎥",String(Math.floor(st.supplied)).padStart(4,"0"));
 }},

/* ---- 7. 다단 컨베이어 캐스케이드 ---- */
cascade:{
 label:"다단 반송 라인 — 하류부터 3초 간격 순차 기동(적체 방지)",
 wiresOut:[["CONV_UP",[[14.72,4.95],[3.4,4.9],[3.4,2.8]]],
           ["CONV_MID",[[14.72,5.0],[8.6,4.95],[8.6,2.8]]],
           ["CONV_DOWN",[[14.72,5.05],[13.6,4.7],[13.6,2.8]]]],
 init:()=>({spd:[0,0,0],ph:[0,0,0],parts:[],spawn:1,count:0}),
 tick(st,o,dt){
   const run=[o.CONV_UP,o.CONV_MID,o.CONV_DOWN];
   for(let i=0;i<3;i++){
     st.spd[i]=ramp(st.spd[i],run[i]?0.85*(cur.speedF||1):0,1.2,dt);
     st.ph[i]=(st.ph[i]+st.spd[i]*dt)%0.55;
   }
   st.spawn-=dt;
   if(st.spd[0]>0.3&&st.spawn<=0&&st.parts.length<10){st.parts.push({x:1.3,b:0,z:1.35,fall:0});st.spawn=2.1/(cur.speedF||1);}
   const ends=[6.0,11.2,16.4],starts=[1.2,6.4,11.6],tops=[1.35,0.95,0.55];
   for(const p of st.parts){
     if(p.fall){p.z-=dt*1.6;p.x+=dt*0.3;
       if(p.b>2){if(p.z<0.2){p.done=1;st.count++;}}
       else if(p.z<=tops[p.b]){p.z=tops[p.b];p.fall=0;p.x=starts[p.b];}
     }else{
       p.x+=st.spd[p.b]*dt;
       if(p.x>ends[p.b]){p.b++;p.fall=1;}
     }
   }
   st.parts=st.parts.filter(p=>!p.done);
 },
 draw(ctx,st,val,t){
   beltUnit(1.0,2.0,5.0,st.ph[0],st.spd[0]>0.02,1.35);
   beltUnit(6.2,2.0,5.0,st.ph[1],st.spd[1]>0.02,0.95);
   beltUnit(11.4,2.0,5.0,st.ph[2],st.spd[2]>0.02,0.55);
   tag3(3.4,2.3,1.55,"CV-601","상류 벨트",val("CONV_UP")?"#7ee787":"#5d6c7c");
   tag3(8.6,2.3,1.15,"CV-602","중간 벨트",val("CONV_MID")?"#7ee787":"#5d6c7c");
   tag3(13.8,2.3,0.75,"CV-603","하류 벨트",val("CONV_DOWN")?"#7ee787":"#5d6c7c");
   dq(6.3+2.3+1.2,c2=>lamp(c2,P(6.15,2.0,1.5),2.6,"#3fb950",val("CONV_UP")));
   dq(11.5+2.3+1,c2=>lamp(c2,P(11.35,2.0,1.1),2.6,"#3fb950",val("CONV_MID")));
   dq(16.5+2.3+0.8,c2=>lamp(c2,P(16.55,2.0,0.7),2.6,"#3fb950",val("CONV_DOWN")));
   st.parts.forEach((p,i)=>{
     box3(p.x-0.15,2.14,p.z,0.3,0.32,0.28,PARTC[i%4]);
   });
   sh(16.6,1.8,1.0,1.0,0.25);
   box3(16.65,1.85,0,0.95,0.9,0.5,"#54442a");
   stackLight(16.0,4.2,st.spd.every(s=>s<0.05),false,st.spd.some(s=>s>0.3));
   ledBoard(4.0,0.9,"반출수량",String(st.count).padStart(4,"0"));
 }}
};

/* 씬별 KPI 액세서: 생산량·재공(WIP)·라인속도 */
SCENES.conveyor.prod=st=>st.count; SCENES.conveyor.wip=st=>st.parts.length; SCENES.conveyor.speed=st=>st.spd;
SCENES.shuttle.prod=st=>st.count;  SCENES.shuttle.wip=st=>st.carry?1:0;     SCENES.shuttle.speed=st=>Math.abs(st.spd);
SCENES.carwash.prod=st=>st.count;  SCENES.carwash.wip=st=>(st.carX>-1&&st.carX<19)?1:0;
SCENES.counter.prod=st=>st.good;   SCENES.counter.wip=st=>st.parts.length;  SCENES.counter.speed=()=>1.1*(cur.speedF||1);
SCENES.weld.prod=st=>st.count;     SCENES.weld.wip=st=>(st.partOn||st.out!==undefined)?1:0;
SCENES.batch.prod=st=>st.count;    SCENES.batch.wip=st=>st.level>0.01?1:0;
SCENES.vision.prod=st=>st.ok; SCENES.vision.wip=st=>st.parts.length;
SCENES.vision.speed=()=>1.0*(cur.speedF||1); SCENES.vision.avail=()=>1;
SCENES.vision.quality=st=>(st.ok+st.ng)>0?(st.ok-(st.leak||0))/(st.ok+st.ng):1;
SCENES.pumps.prod=st=>Math.floor(st.supplied); SCENES.pumps.wip=st=>Math.round(st.level*100);
SCENES.pumps.avail=()=>1;
SCENES.conveyor.speedCtl=SCENES.counter.speedCtl=SCENES.cascade.speedCtl=true;
SCENES.counter.overhead="oht"; SCENES.vision.overhead="oht"; SCENES.weld.overhead="oht";
SCENES.batch.overhead="piping"; SCENES.pumps.overhead="piping"; SCENES.carwash.overhead="piping";
/* conveyor·shuttle·cascade = 기본 crane */
SCENES.cascade.prod=st=>st.count;  SCENES.cascade.wip=st=>st.parts.length;  SCENES.cascade.speed=st=>Math.max(...st.spd);

SCENES.counter.quality=st=>(st.good+st.ejected)>0?st.good/(st.good+st.ejected):1;
SCENES.counter.avail=()=>1; /* 검수 라인 벨트는 상시 가동(배출 실린더는 간헐 작동) */

/* 알람·이벤트 로그 */
function logEv(lv,msg){
  if(!cur)return;
  const t=(performance.now()-cur.kpi.t0)/1000;
  cur.log.unshift({lv,msg,t:"T+"+t.toFixed(1)+"s"});
  if(cur.log.length>60)cur.log.pop();
}

/* 택타임·전력 추이 차트 */
function drawTrend(){
  const tc=document.getElementById("trend");if(!tc)return;
  const dpr=window.devicePixelRatio||1,W=tc.clientWidth,H=tc.clientHeight;
  if(tc.width!==(W*dpr|0)){tc.width=W*dpr;tc.height=H*dpr;}
  const c=tc.getContext("2d");c.setTransform(dpr,0,0,dpr,0,0);c.clearRect(0,0,W,H);
  const D=cur.trend;
  if(D.length<3){c.fillStyle="#5d6c7c";c.font="10px ui-monospace";
    c.fillText("가동 데이터 수집 중…",10,18);return;}
  const cfg=KPI[cur.id]||{};
  const panes=[
   {title:"생산 누계 EA",col:"#3fd97a",fill:"rgba(63,217,122,.12)",get:p=>p.prod,area:true},
   {title:"택타임 s/개"+(cfg.tt?" (점선=목표 "+cfg.tt+"s)":""),col:"#58a6ff",get:p=>p.takt,ref:cfg.tt},
   {title:"소비 전력 kW",col:"#b9a3ff",fill:"rgba(185,163,255,.12)",get:p=>p.kw,area:true}
  ];
  const pw=(W-24)/3;
  panes.forEach((pn,pi)=>{
    const x0=8+pi*(pw+4), y0=16, ph2=H-30;
    c.fillStyle="#6f7a8a";c.font="9.5px ui-monospace";c.textAlign="left";
    c.fillText(pn.title,x0,11);
    const vals=D.map(pn.get).filter(v=>v!==null&&!isNaN(v));
    if(!vals.length){c.fillText("—",x0,y0+20);return;}
    const vmax=Math.max(...vals,pn.ref||0)*1.15+1e-6, vmin=0;
    /* 축·눈금 */
    c.strokeStyle="rgba(90,105,120,.4)";c.lineWidth=1;
    c.strokeRect(x0,y0,pw-8,ph2);
    c.textAlign="right";
    for(const f of[0,0.5,1]){
      const yy=y0+ph2-(ph2-4)*f-2;
      c.fillStyle="#4a5663";c.fillText((vmin+(vmax-vmin)*f).toFixed(vmax>20?0:1),x0+pw-12,yy+3);
      c.strokeStyle="rgba(90,105,120,.18)";
      c.beginPath();c.moveTo(x0+1,yy);c.lineTo(x0+pw-9,yy);c.stroke();
    }
    const X=i=>x0+2+(pw-14)*i/(D.length-1);
    const Y=v=>y0+ph2-2-(ph2-6)*(v-vmin)/(vmax-vmin);
    if(pn.ref){
      c.setLineDash([4,4]);c.strokeStyle="rgba(217,165,20,.7)";
      c.beginPath();c.moveTo(x0+2,Y(pn.ref));c.lineTo(x0+pw-10,Y(pn.ref));c.stroke();
      c.setLineDash([]);
    }
    c.strokeStyle=pn.col;c.lineWidth=1.6;c.beginPath();let st0=false;
    D.forEach((p,i)=>{const v=pn.get(p);if(v===null||isNaN(v))return;
      const xx=X(i),yy=Y(v);st0?c.lineTo(xx,yy):(c.moveTo(xx,yy),st0=true);});
    c.stroke();
    if(pn.area){
      c.lineTo(X(D.length-1),y0+ph2-2);c.lineTo(X(0),y0+ph2-2);c.closePath();
      c.fillStyle=pn.fill;c.fill();
    }
    const last=vals[vals.length-1];
    c.fillStyle=pn.col;c.textAlign="left";c.font="700 11px ui-monospace";
    c.fillText(typeof last==="number"?(last>=100?last.toFixed(0):last.toFixed(1)):"—",x0+4,y0+12);
  });
}

/* ============================================================
   메인 루프 — 센서 → 스캔 → 물리 → 렌더 → DOM(쓰로틀)
   ============================================================ */
let cur=null,rafId=0,lastT=0,domT=0;
function effL(L,sym){
  for(const f of (L.m.faults||[]))
    if(f.type==="trip"&&f.sym===sym&&L.faults[f.id])return false;
  return L.plc.val(sym);
}
function eff(sym){return effL(cur,sym);}
const LINES={};
const OV={motor_start_stop:"포장 컨베이어",fwd_rev:"이송 대차",car_wash:"세차 터널",
  count_eject:"검수 카운트",conveyor_divert:"비전 분기",weld_cell:"용접 셀",
  batch_fill_mix_drain:"배치 플랜트",duty_standby:"급수 펌프장",cascade_conveyor:"다단 반송"};

/* ---- 자동 시연 오토파일럿: 라인별 가상 조작 시퀀스 ---- */
const AUTO={
 motor_start_stop(L){if(!L.plc.val("MOTOR"))return["START",0.3,2];},
 fwd_rev(L){const st=L.sst;
   if(st.anim>0)return null;
   const f=L.plc.val("MOTOR_FWD"),r=L.plc.val("MOTOR_REV");
   if(f||r){
     if(st.carry&&st.pos>=12.4)return["STOP",0.3,1.5];
     if(!st.carry&&st.pos<=2.1)return["STOP",0.3,1.5];
     return null;}
   if(st.carry)return["FWD_PB",0.3,1.5];
   if(st.pos>2.15)return["REV_PB",0.3,1.5];
   return null;},
 car_wash(L){const on=["SOAP","RINSE","DRY"].some(x=>L.plc.val(x));
   if(!on&&L.sst.carX<=-1.3&&!L.sst.exiting)return["START",0.4,3];},
 count_eject(L){const c=L.plc.counters.C1;
   if(c&&c.q)return["RESET_PB",0.4,4];},
 conveyor_divert(L){if(!L.plc.val("GATE_A")&&!L.plc.val("GATE_B")&&L.sst.sel===0)return["SEL_A",0.3,2];},
 weld_cell(L){const busy=["CLAMP","WELD","UNCLAMP"].some(x=>L.plc.val(x));
   if(!busy&&L.sst.partOn)return["WELD_START",0.3,2];},
 batch_fill_mix_drain(L){const busy=["FILL_VALVE","MIXER","DRAIN_VALVE"].some(x=>L.plc.val(x));
   if(!busy&&!L.sst.exit)return["START",0.3,2];},
 duty_standby(){return null;},
 cascade_conveyor(L){if(L.sst.spd.every(v=>v<0.02)&&!L.plc.val("CONV_DOWN"))return["START_PB",0.4,6];}
};
function autopilot(L,dt){
  if(!L.auto)return;
  if(L.apPulse){L.apPulse.t-=dt;
    if(L.apPulse.t<=0){L.plc.set(L.apPulse.sym,false);L.apPulse=null;}
    return;}
  L.apCool=(L.apCool||0)-dt;
  if(L.apCool>0)return;
  const a=AUTO[L.id]&&AUTO[L.id](L);
  if(a){L.plc.set(a[0],true);L.apPulse={sym:a[0],t:a[1]};L.apCool=a[2]||1.5;}
}
function lineOEE(L){
  const K=L.kpi,cfg=KPI[L.id]||{};
  const elapsed=Math.max(0.001,(performance.now()-K.t0)/1000);
  const mainSym=Object.keys(L.m.tags||{})[0];
  const A=L.scene.avail?L.scene.avail(L.sst)
    :(mainSym&&L.stats[mainSym]?Math.min(1,L.stats[mainSym].rt/elapsed):0);
  const Pf=K.taktAvg&&cfg.tt?Math.min(1,cfg.tt/K.taktAvg):null;
  const Q=L.scene.quality?L.scene.quality(L.sst):1;
  return Pf===null?null:A*Pf*Q*100;
}
function drawScene(t){
  if(cvs.clientWidth!==view.W||cvs.clientHeight!==view.H)resize();
  const ctx=g2;
  ctx.clearRect(0,0,view.W,view.H);
  CHIPS.length=0;
  cam.z+=(camT.z-cam.z)*0.22; cam.px+=(camT.px-cam.px)*0.22; cam.py+=(camT.py-cam.py)*0.22;
  ctx.save();
  ctx.translate(cam.px,cam.py);
  ctx.scale(cam.z,cam.z);
  floorGrid(ctx);
  const val=eff;
  const [wopx,wopy]=LP("op"),[wplx,wply]=LP("plc");
  cur.m.buttons.forEach((b,i)=>wirePath(ctx,
    [[wopx+0.36,wopy+0.33+i*0.09],[(wopx+wplx)/2+0.4,Math.max(wopy,wply)+0.85],[wplx+0.02,wply+0.4+i*0.05]],
    val(b.sym),t,"#58a6ff"));
  const TB=[10.91,4.62];
  (cur.scene.wiresIn||[]).forEach(([s,pts])=>
    wirePath(ctx,pts.slice(0,-1).concat([TB,[wplx-0.04,wply+0.22]]),val(s),t,"#58a6ff"));
  (cur.scene.wiresOut||[]).forEach(([s,pts],i)=>
    wirePath(ctx,[[wplx+0.02,wply+0.06+i*0.06],[TB[0],TB[1]+i*0.04]].concat(pts.slice(1)),val(s),t,"#3fb950"));
  cur.scene.draw(ctx,cur.sst,val,t);
  chrome(ctx,t,val);
  drawShadows(ctx);
  flushQ(ctx);
  drawLabels(ctx);
  ctx.restore();
  txt(ctx,[14,20],cur.scene.label,"#aebdcd",12.5,"left",true);
  txt(ctx,[14,37],"드래그=이동 · 휠=줌 · 더블클릭=초기화 · 기기 라벨 클릭=상세 — 1유닛=1m 실측","#5d6c7c",11,"left");
  const K=cur.kpi,cfg=KPI[cur.id]||{unit:"개"};
  const hud=[
   ["생산",(cur.scene.prod?cur.scene.prod(cur.sst):0)+" "+cfg.unit],
   ["택타임",K.taktAvg?K.taktAvg.toFixed(1)+" s":"측정중"],
   ["UPH",K.taktAvg?String(Math.round(3600/K.taktAvg)):"—"],
   ["전력",K.kw.toFixed(1)+" kW"]];
  let hy=22;
  for(const[k,v]of hud){
    txt(ctx,[view.W-118,hy],k,"#5d6c7c",10,"left");
    txt(ctx,[view.W-14,hy],v,"#9fe0b0",11.5,"right",true);
    hy+=16;
  }
}
function updateDOM(r,dt,t){
  const d=cur.d;
  d.sim.inputs.forEach(s=>{const el=document.getElementById("dot_"+s);if(el)el.className="dot"+(cur.plc.val(s)?" on-i":"");});
  d.sim.outputs.forEach(s=>{const el=document.getElementById("dot_"+s);if(el)el.className="dot"+(cur.plc.val(s)?" on-o":"");});
  for(const[s,tm]of Object.entries(cur.plc.timers)){
    const dd=document.getElementById("dot_"+s);if(dd)dd.className="dot"+(tm.q?" on-o":"");
    const bar=document.getElementById("bar_"+s);if(bar)bar.style.width=Math.round(tm.acc/tm.preset*100)+"%";
    const bt=document.getElementById("bt_"+s);if(bt)bt.textContent=`${tm.acc.toFixed(1)}s / ${tm.preset}s${tm.q?" · Q=ON":""}`;
  }
  for(const[s,cn]of Object.entries(cur.plc.counters)){
    const dd=document.getElementById("dot_"+s);if(dd)dd.className="dot"+(cn.q?" on-o":"");
    const bar=document.getElementById("bar_"+s);if(bar)bar.style.width=Math.round(cn.cnt/cn.preset*100)+"%";
    const bt=document.getElementById("bt_"+s);if(bt)bt.textContent=`${cn.cnt} / ${cn.preset}${cn.q?" · Q=ON":""}`;
  }
  document.getElementById("scaninfo").innerHTML=
    `<span>스캔 <b>#${cur.scanN}</b></span><span>주기 <b>${(dt*1000).toFixed(1)}ms</b></span>`+
    `<span>로직 평가 <b>${cur.us<1?"&lt;1":cur.us.toFixed(1)}µs</b></span>`+
    `<span>상태 <b>RUN</b></span><span>이중코일 <b>0</b></span>`+
    (COSIM.on&&COSIM.ready?`<span style="color:#7ee787">⚡ 서버 코사임 t=${(COSIM.t_ms/1000).toFixed(2)}s · 10ms 정밀</span>`:"");
  const rows=[];
  let idx=0;
  for(const[sym,info]of Object.entries(cur.m.tags||{})){
    const stt=cur.stats[sym], on=eff(sym);
    const tripped=(cur.m.faults||[]).some(f=>f.type==="trip"&&f.sym===sym&&cur.faults[f.id]);
    const cur_a=on?(info.rated*(0.93+0.05*Math.sin(t*6+idx))).toFixed(1):"0.0";
    const load=on?Math.round(58+20*Math.sin(t*0.5+idx*2)+8*Math.sin(t*2.2+idx)):0;
    if(on&&load>80&&(!stt.lastOvl||t-stt.lastOvl>20)){
      stt.lastOvl=t;
      logEv("warn",`${info.tag} 부하 ${load}% — 과부하 주의`);
    }
    rows.push(`<tr><td><b>${info.tag}</b></td><td class="mut">${info.name}</td>`+
      `<td style="color:${tripped?"#f85149":on?"#3fb950":"#8b98a8"};font-weight:${tripped?700:400}">${tripped?"TRIP":on?"RUN":"STOP"}</td>`+
      `<td class="mut">${stt.rt.toFixed(0)}s</td><td class="mut">${stt.starts}</td>`+
      `<td class="mut">${cur_a}A</td><td class="mut">${on?load+"%":"—"}</td></tr>`);
    idx++;
  }
  document.getElementById("opstable").innerHTML=
    `<tr><td class="mut">기기</td><td class="mut">설비명</td><td class="mut">상태</td><td class="mut">가동</td><td class="mut">기동</td><td class="mut">전류</td><td class="mut">부하</td></tr>`+rows.join("");
  const K=cur.kpi, cfg=KPI[cur.id]||{unit:"개",w:null};
  const prodN=cur.scene.prod?cur.scene.prod(cur.sst):0;
  const nowMs=performance.now();
  const elapsed=Math.max(0.001,(nowMs-K.t0)/1000);
  const mainSym=Object.keys(cur.m.tags||{})[0];
  const util=cur.scene.avail?cur.scene.avail(cur.sst)*100
    :(mainSym&&cur.stats[mainSym]?Math.min(100,cur.stats[mainSym].rt/elapsed*100):0);
  const wip=cur.scene.wip?cur.scene.wip(cur.sst):0;
  const spd=cur.scene.speed?cur.scene.speed(cur.sst):null;
  const uph=K.taktAvg?3600/K.taktAvg:0;
  const fmt=(v,d)=>v===null||isNaN(v)?"—":v.toFixed(d);
  const A=util/100;
  const Pf=K.taktAvg&&cfg.tt?Math.min(1,cfg.tt/K.taktAvg):null;
  const Q=cur.scene.quality?cur.scene.quality(cur.sst):1;
  const oee=Pf!==null?A*Pf*Q*100:null;
  if(K.taktAvg&&cfg.tt){
    if(K.taktAvg>cfg.tt*1.3&&!cur.taktAlarm){cur.taktAlarm=true;logEv("warn",`택타임 ${K.taktAvg.toFixed(1)}s — 목표 ${cfg.tt}s 초과`);}
    if(K.taktAvg<cfg.tt*1.1)cur.taktAlarm=false;
  }
  const cards=[
   [oee!==null?fmt(oee,0)+"%":"측정중",`OEE = A ${fmt(util,0)}% × P ${Pf!==null?fmt(Pf*100,0):"—"}% × Q ${fmt(Q*100,0)}%`,oee!==null&&oee<55?"amber":""],
   [String(prodN),`생산수량 (${cfg.unit})`,""],
   [K.taktAvg?fmt(K.taktAvg,1)+"s":"측정중",`택타임 / ${cfg.unit}`+(cfg.tt?` · 목표 ${cfg.tt}s`:""), K.taktAvg&&cfg.tt&&K.taktAvg>cfg.tt*1.25?"amber":""],
   [uph?String(Math.round(uph)):"—","시간당 생산 UPH",""],
   [cfg.w!==null?fmt(cfg.w,1)+" kg":"—",`개당 중량 / ${cfg.unit}`,"blue"],
   [cfg.w!==null?fmt(prodN*cfg.w,0)+" kg":"—","누적 생산 중량","blue"],
   [String(wip),"재공 WIP (라인 위)",""],
   [spd!==null?fmt(spd,2)+" m/s":"—","라인 속도","blue"],
   [fmt(util,0)+"%","주설비 가동률",util<40?"amber":""],
   [fmt(K.kw,1)+" kW","현재 소비 전력","blue"],
   ...(cur.scene.quality?[[fmt((1-Q)*100,1)+"%","불량율 — 검사 실측",(1-Q)>0.12?"amber":""]]:[]),
   [fmt(K.kwh*1000,1)+" Wh","누적 전력량","blue"]];
  document.getElementById("kpis").innerHTML=cards.map(([v,l,cl])=>
   `<div class="kpi"><b class="${cl}">${v}</b><span>${l}</span></div>`).join("");
  if(nowMs-cur.lastTrendT>1500){
    cur.lastTrendT=nowMs;
    cur.trend.push({takt:K.taktAvg,kw:K.kw,prod:prodN,oee:oee===null?null:oee});
    if(cur.trend.length>120)cur.trend.shift();
    drawTrend();
  }
  for(const[addr,a]of Object.entries(cur.m.analog||{})){
    const el2=document.getElementById("an_"+addr);
    if(el2)el2.textContent=String(a.get(cur.sst,cur));
  }
  for(const[addr,,get]of dRegs(cur)){
    const el2=document.getElementById("an_"+addr);
    if(el2)el2.textContent=String(get());
  }
  if(devOpen)renderDevLive();
  document.getElementById("alarms").innerHTML=cur.log.slice(0,40).map(e=>
   `<div class="alm ${e.lv}"><i></i><span class="t">${e.t}</span><span>${e.msg}</span></div>`).join("")
   ||'<div class="alm"><i></i><span class="t">—</span><span>이벤트 없음</span></div>';
  const key=JSON.stringify(r.en)
    +Object.values(cur.plc.timers).map(tm=>Math.round(tm.acc*10)).join()
    +Object.values(cur.plc.counters).map(cn=>cn.cnt).join();
  if(key!==cur.lastKey){
    cur.lastKey=key;
    document.getElementById("ladder").innerHTML=ladderLive(d.ladder,r.en,cur.plc,cur.m.addr);
    const wd=document.getElementById("wiring");
    if(wd)wd.innerHTML=wiringSvg(cur);
  }
}
/* ---- 카메라(줌·팬) + 기기 클릭 상세 ---- */
let pdrag=null,devOpen=null;
const COSIM={ws:null,on:false,ready:false,acc:0,lastSent:{},t_ms:0,pend:0,line:null};
cvs.addEventListener("wheel",e=>{
  e.preventDefault();
  const r=cvs.getBoundingClientRect(),mx=e.clientX-r.left,my=e.clientY-r.top;
  const nz=Math.min(8,Math.max(0.55,camT.z*Math.exp(-e.deltaY*0.0012)));
  const kk=nz/camT.z;
  camT.px=mx-(mx-camT.px)*kk; camT.py=my-(my-camT.py)*kk; camT.z=nz;
},{passive:false});
cvs.addEventListener("pointerdown",e=>{
  if(editMode){
    const hit=chipAt(e);
    if(hit&&EDITKEY[hit.tg]){
      const k=EDITKEY[hit.tg],o=LAYOUT[k]||{dx:0,dy:0};
      eDrag={key:k,sx:e.clientX,sy:e.clientY,dx0:o.dx,dy0:o.dy};
      cvs.setPointerCapture(e.pointerId);
      return;
    }
  }
  pdrag={x:e.clientX,y:e.clientY,px:camT.px,py:camT.py,moved:false};
  cvs.setPointerCapture(e.pointerId);
});
cvs.addEventListener("pointermove",e=>{
  if(eDrag){
    const sN=view.s*cam.z;
    const dsx=e.clientX-eDrag.sx, dsy=e.clientY-eDrag.sy;
    const dwx=(dsx/(0.866*sN)+dsy/(0.5*sN))/2, dwy=(dsy/(0.5*sN)-dsx/(0.866*sN))/2;
    const d0=DEF_POS[eDrag.key];
    let nx=eDrag.dx0+dwx, ny=eDrag.dy0+dwy;
    nx=Math.max(0.4-d0[0],Math.min(15.8-d0[0],nx));
    ny=Math.max(4.2-d0[1],Math.min(7.0-d0[1],ny));
    LAYOUT[eDrag.key]={dx:nx,dy:ny};
    return;
  }
  if(!pdrag)return;
  const dx=e.clientX-pdrag.x,dy=e.clientY-pdrag.y;
  if(Math.abs(dx)+Math.abs(dy)>5)pdrag.moved=true;
  camT.px=pdrag.px+dx; camT.py=pdrag.py+dy;
});
cvs.addEventListener("pointerup",e=>{
  if(eDrag){
    try{localStorage.setItem("hands_layout",JSON.stringify(LAYOUT));}catch(e2){}
    logEv("op","배치 변경 저장 — "+eDrag.key.toUpperCase());
    eDrag=null;
    return;
  }
  if(pdrag&&!pdrag.moved)pickDevice(e);
  pdrag=null;
});
cvs.addEventListener("dblclick",()=>{camT={z:1,px:0,py:0};hideDev();});
document.getElementById("lblbtn").onclick=()=>{
  labelMode=(labelMode+1)%3;
  document.getElementById("lblbtn").textContent="라벨: "+["숨김","핵심","전체"][labelMode];
};
document.getElementById("editbtn").onclick=()=>{
  editMode=!editMode;
  document.getElementById("editbtn").classList.toggle("on",editMode);
  document.getElementById("rstbtn").style.display=editMode?"block":"none";
  logEv("op",editMode?"배치 편집 시작 — OP-01·PLC-01·AVR-01·STG-01 드래그로 이동":"배치 편집 종료");
};
document.getElementById("setbtn").onclick=()=>{
  document.getElementById("setwrap").style.display="block";
};
document.getElementById("viewbtn").onclick=()=>{
  VIEW_MODE=VIEW_MODE==="iso"?"top":"iso";
  document.getElementById("viewbtn").textContent="시점: "+(VIEW_MODE==="iso"?"아이소":"탑뷰(천장)");
  logEv("op","시점 전환 → "+(VIEW_MODE==="iso"?"아이소메트릭":"탑뷰"));
};
document.getElementById("setclose").onclick=()=>{
  document.getElementById("setwrap").style.display="none";
};
document.getElementById("setwrap").addEventListener("click",e=>{
  if(e.target.id==="setwrap")document.getElementById("setwrap").style.display="none";
});
document.getElementById("rstbtn").onclick=()=>{
  LAYOUT={};
  try{localStorage.removeItem("hands_layout");}catch(e2){}
  logEv("op","배치 초기화 — 기본 위치 복원");
};
function chipAt(e){
  const r=cvs.getBoundingClientRect();
  const mx=(e.clientX-r.left-cam.px)/cam.z, my=(e.clientY-r.top-cam.py)/cam.z;
  return CHIPS.find(c=>(mx>=c.bx-3&&mx<=c.bx+c.w+3&&my>=c.by-3&&my<=c.by+c.h+3)
    ||Math.hypot(mx-c.ax,my-c.ay)<14);
}
function pickDevice(e){
  const hit=chipAt(e);
  if(hit){devOpen=hit.tg;
    const rb=cvs.getBoundingClientRect();
    const el=document.getElementById("devpanel");
    el.style.display="block";
    el.style.left=Math.max(6,Math.min(e.clientX-rb.left+14,cvs.clientWidth-248))+"px";
    el.style.top=Math.max(6,Math.min(e.clientY-rb.top+6,cvs.clientHeight-160))+"px";
    renderDev();
  } else hideDev();
}
function renderDev(){
  if(!devOpen)return;
  const el=document.getElementById("devpanel");
  const ent=Object.entries(cur.m.tags||{}).find(([,i2])=>i2.tag===devOpen);
  const chip=CHIPS.find(c=>c.tg===devOpen);
  let h=`<div class="dvt">${devOpen}</div>`;
  if(ent){
    const[sym,info]=ent, stt=cur.stats[sym], on=eff(sym);
    const tripped=(cur.m.faults||[]).some(f=>f.type==="trip"&&f.sym===sym&&cur.faults[f.id]);
    const t2=performance.now()/1000;
    const amp=on?(info.rated*(0.93+0.05*Math.sin(t2*6))).toFixed(1):"0.0";
    h+=`<div class="dvr"><span>설비</span><b>${info.name}</b></div>`+
     `<div class="dvr"><span>신호 · 주소</span><b>${sym} · ${cur.m.addr[sym]||"—"}</b></div>`+
     `<div class="dvr"><span>상태</span><b id="dvv_state" style="color:${tripped?"#f85149":on?"#3fb950":"#8b98a8"}">${tripped?"TRIP — 복구 필요":on?"RUN":"STOP"}</b></div>`+
     `<div class="dvr"><span>전류 / 정격</span><b id="dvv_amp">${amp} A / ${info.rated} A</b></div>`+
     `<div class="dvr"><span>가동 · 기동</span><b id="dvv_run">${stt.rt.toFixed(0)}s · ${stt.starts}회</b></div>`;
  }else{
    h+=`<div class="dvr"><span>유형</span><b>${(chip&&chip.sub)||"계측·구조물"}</b></div>`+
     `<div class="dvr"><span>제어</span><b>PLC 비구동(수동/센서)</b></div>`;
  }
  /* 기기별 파라미터 입력 — 현장 셋업처럼 */
  if(devOpen==="VS-701"){
    const c=visionCfg(cur),op2=visionOptics(cur);
    h+=`<div class="dvt" style="margin-top:9px">광학 셋업(FOV·렌즈·조도)</div>`+
     `<div class="dvr"><span>렌즈 f</span><b><select id="dv_f" style="background:#0a0f17;color:#cdd6e3;border:1px solid #2b3743;border-radius:5px">`+
     [8,12,16,25,35].map(v=>`<option ${v===c.f?"selected":""}>${v}</option>`).join("")+`</select> mm</b></div>`+
     `<div class="dvr"><span>WD 작동거리</span><b><input id="dv_wd" type="number" value="${c.wd}" style="width:64px;background:#0a0f17;color:#cdd6e3;border:1px solid #2b3743;border-radius:5px"/> mm</b></div>`+
     `<div class="dvr"><span>조도</span><b><input id="dv_lux" type="range" min="50" max="1200" value="${c.lux}" style="width:90px"/> <span id="dv_luxv">${c.lux}</span> lx</b></div>`+
     `<div class="dvr"><span>FOV / 분해능</span><b id="dv_calc">${op2.fovW.toFixed(0)}×${op2.fovH.toFixed(0)}mm · ${op2.res.toFixed(0)}µm/px</b></div>`+
     `<div class="dvr"><span>검출 신뢰도</span><b id="dv_conf" style="color:${op2.conf>0.85?"#7ee787":"#f0c26b"}">${(op2.conf*100).toFixed(0)}%</b></div>`;
  }
  if(devOpen==="RB-401"){
    h+=`<button class="xbtn" style="margin-top:9px;width:100%" onclick="openPendant()">🎛 티칭 펜던트 열기</button>`;
  }
  if(ent&&ent[1].rated!==undefined){
    h+=`<div class="dvr"><span>정격 전류 설정</span><b><input id="dv_rated" type="number" step="0.1" value="${ent[1].rated}" style="width:64px;background:#0a0f17;color:#cdd6e3;border:1px solid #2b3743;border-radius:5px"/> A</b></div>`;
    if(devOpen==="M-101")
      h+=`<div class="dvr"><span>가감속</span><b><input id="dv_acc" type="number" step="0.1" value="${((cur.devCfg["M-101"]||{}).acc)||1.4}" style="width:64px;background:#0a0f17;color:#cdd6e3;border:1px solid #2b3743;border-radius:5px"/> m/s²</b></div>`;
  }
  h+=`<button class="xbtn" onclick="hideDev()" style="margin-top:8px">닫기</button>`;
  el.innerHTML=h;
  /* 입력 바인딩 */
  const c3=visionCfg(cur);
  const upd=()=>{const op3=visionOptics(cur);
    const e1=document.getElementById("dv_calc");
    if(e1)e1.textContent=`${op3.fovW.toFixed(0)}×${op3.fovH.toFixed(0)}mm · ${op3.res.toFixed(0)}µm/px`;
    const e2=document.getElementById("dv_conf");
    if(e2){e2.textContent=(op3.conf*100).toFixed(0)+"%";e2.style.color=op3.conf>0.85?"#7ee787":"#f0c26b";}};
  const fE=document.getElementById("dv_f");
  if(fE)fE.onchange=()=>{c3.f=+fE.value;logEv("op","VS-701 렌즈 변경 → f"+c3.f+"mm");upd();};
  const wdE=document.getElementById("dv_wd");
  if(wdE)wdE.onchange=()=>{c3.wd=Math.max(50,+wdE.value||300);logEv("op","VS-701 WD → "+c3.wd+"mm");upd();};
  const lxE=document.getElementById("dv_lux");
  if(lxE)lxE.oninput=()=>{c3.lux=+lxE.value;
    document.getElementById("dv_luxv").textContent=c3.lux;upd();};
  const rtE=document.getElementById("dv_rated");
  if(rtE&&ent)rtE.onchange=()=>{const v=parseFloat(rtE.value);
    if(v>0){ent[1].rated=v;logEv("op",devOpen+" 정격 전류 → "+v+"A");}};
  const acE=document.getElementById("dv_acc");
  if(acE)acE.onchange=()=>{const v=parseFloat(acE.value);
    if(v>0){(cur.devCfg["M-101"]=cur.devCfg["M-101"]||{}).acc=v;logEv("op","M-101 가감속 → "+v+"m/s²");}};
}

/* ── 로봇 티칭 펜던트 ── */
function openPendant(){
  const rc=cur.devCfg["RB-401"]||(cur.devCfg["RB-401"]={off:[0,0,0],spd:100});
  if(!rc.off)rc.off=[0,0,0];
  const el=document.getElementById("pendant");
  el.style.display="block";
  const fmt=()=>`P3 WELD = (${(7.55+rc.off[0]).toFixed(2)}, ${(2.30+rc.off[1]).toFixed(2)}, ${(1.04+rc.off[2]).toFixed(2)}) m`;
  el.innerHTML=
   `<div class="alhd"><h4>🎛 RB-401 티칭 펜던트</h4><button class="xbtn" onclick="document.getElementById('pendant').style.display='none'">닫기 ✕</button></div>`+
   `<div class="fitbox" style="margin-top:10px">포인트 목록<br/>P1 HOME = (6.85, 2.95, 2.00)<br/>P2 APPROACH = (7.20, 2.60, 1.50)<br/><b id="pd_p3" style="color:#7ee787">${fmt()}</b></div>`+
   `<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:6px;margin:10px 0">`+
   [["X−",0,-1],["Y−",1,-1],["Z−",2,-1],["X+",0,1],["Y+",1,1],["Z+",2,1]].map(([lb,ax,dr])=>
     `<button class="fbtn abtn" data-jog="${ax},${dr}">${lb} JOG</button>`).join("")+`</div>`+
   `<div class="sld" style="margin:6px 0"><small>속도 오버라이드 <b id="pd_spdv">${rc.spd||100}%</b></small>`+
   `<input id="pd_spd" type="range" min="10" max="100" value="${rc.spd||100}" style="width:100%"/></div>`+
   `<div style="display:flex;gap:8px;margin-top:10px">`+
   `<button class="xbtn" id="pd_save" style="flex:1">P3 저장(티칭 확정)</button>`+
   `<button class="xbtn" id="pd_reset">원점 복귀</button></div>`+
   `<div class="hint" style="font-size:11.5px;color:var(--mut);margin-top:10px">JOG ±0.05m — 토치 타깃이 3D에서 즉시 이동합니다. 지그 범위(±0.4m) 밖 티칭 시 용접 품질 저하.</div>`;
  el.querySelectorAll("[data-jog]").forEach(b=>{
    b.onclick=()=>{const[ax,dr]=b.dataset.jog.split(",").map(Number);
      rc.off[ax]=Math.max(-0.4,Math.min(0.4,rc.off[ax]+dr*0.05));
      document.getElementById("pd_p3").textContent=fmt();};
  });
  document.getElementById("pd_spd").oninput=e=>{
    rc.spd=+e.target.value;
    document.getElementById("pd_spdv").textContent=rc.spd+"%";};
  document.getElementById("pd_save").onclick=()=>{
    logEv("op",`RB-401 티칭 저장 — ${fmt()} · 속도 ${rc.spd||100}%`);};
  document.getElementById("pd_reset").onclick=()=>{
    rc.off=[0,0,0];document.getElementById("pd_p3").textContent=fmt();
    logEv("op","RB-401 원점 복귀(티칭 리셋)");};
}
function renderDevLive(){
  if(!devOpen)return;
  const ent=Object.entries(cur.m.tags||{}).find(([,i2])=>i2.tag===devOpen);
  if(!ent)return;
  const[sym,info]=ent, stt=cur.stats[sym], on=eff(sym);
  const tripped=(cur.m.faults||[]).some(f=>f.type==="trip"&&f.sym===sym&&cur.faults[f.id]);
  const e1=document.getElementById("dvv_state");
  if(e1){e1.textContent=tripped?"TRIP — 복구 필요":on?"RUN":"STOP";
    e1.style.color=tripped?"#f85149":on?"#3fb950":"#8b98a8";}
  const t2=performance.now()/1000;
  const e2=document.getElementById("dvv_amp");
  if(e2)e2.textContent=(on?(info.rated*(0.93+0.05*Math.sin(t2*6))).toFixed(1):"0.0")+" A / "+info.rated+" A";
  const e3=document.getElementById("dvv_run");
  if(e3)e3.textContent=stt.rt.toFixed(0)+"s · "+stt.starts+"회";
}
function hideDev(){devOpen=null;const el=document.getElementById("devpanel");if(el)el.style.display="none";}

function simLine(L,dt,t){
  const prev=cur; cur=L;
  autopilot(L,dt);
  if(L.scene.sense)L.scene.sense(L.sst,L.plc);
  for(const f of (L.m.faults||[]))
    if(f.type==="stuck_on"&&L.faults[f.id])L.plc.set(f.sym,true);
  const r=L.plc.scan(dt);L.scanN++;
  L.us=L.us?L.us*0.9+r.us*0.1:r.us;
  const o={};L.d.sim.outputs.forEach(s2=>{o[s2]=effL(L,s2);
    const stt=L.stats[s2];if(stt){if(o[s2]){stt.rt+=dt;if(!stt.prev)stt.starts++;}stt.prev=o[s2];}});
  for(const sym of L.d.sim.outputs){
    const on=o[sym];
    if(on!==!!L.prevO[sym]){
      const tg=L.m.tags[sym]?L.m.tags[sym].tag+" "+L.m.tags[sym].name:sym;
      logEv(on?"info":"op",tg+(on?" 기동":" 정지"));
      L.prevO[sym]=on;
    }
  }
  for(const b of L.m.buttons){
    const on=L.plc.val(b.sym);
    if(on&&!L.prevI[b.sym]){
      const auto=(L.m.autoInputs&&L.m.autoInputs[b.sym])||(L.apPulse&&L.apPulse.sym===b.sym)||L.auto;
      logEv(b.c==="#c93c3c"?"warn":"op",(auto?"자동 시연: ":"조작: ")+b.label+" ("+b.sym+" ON)");
    }
    L.prevI[b.sym]=on;
  }
  for(const[sym,tm]of Object.entries(L.plc.timers)){
    if(tm.q&&!L.prevQ[sym])logEv("info",sym+" 타이머 완료("+tm.preset+"s) — 단계 전환");
    L.prevQ[sym]=tm.q;
  }
  for(const[sym,cn]of Object.entries(L.plc.counters)){
    if(cn.q&&!L.prevQ[sym])logEv("warn",sym+" 카운트 "+cn.preset+" 도달 — 배출 작동");
    L.prevQ[sym]=cn.q;
  }
  let kw=0;
  for(const[sym,info]of Object.entries(L.m.tags||{}))
    if(effL(L,sym))kw+=1.732*380*info.rated*0.85/1000;
  L.kpi.kw=kw; L.kpi.kwh+=kw*dt/3600;
  const prodN=L.scene.prod?L.scene.prod(L.sst):0;
  const K=L.kpi, nowMs=performance.now();
  if(prodN>K.lastN){
    if(K.lastDoneT!==null){
      const tk=(nowMs-K.lastDoneT)/1000/(prodN-K.lastN);
      K.takt=tk; K.taktAvg=K.taktAvg===null?tk:K.taktAvg*0.7+tk*0.3;
    }
    K.lastDoneT=nowMs; K.lastN=prodN;
  }
  if(COSIM.on&&COSIM.line===L.id)cosimPump(L,dt);
  L.scene.tick(L.sst,o,dt);
  cur=prev;
  return r;
}
function loop(now){
  rafId=requestAnimationFrame(loop);
  const dt=Math.min((now-lastT)/1000,0.05);lastT=now;
  let rActive=null;
  for(const id of ids){
    const r=simLine(LINES[id],dt,now/1000);
    if(LINES[id]===cur)rActive=r;
  }
  drawScene(now/1000);
  if(now-domT>90){domT=now;updateDOM(rActive,dt,now/1000);updateOverview();}
}
let _ovHtml="";
function updateOverview(){
  const el=document.getElementById("overview");if(!el)return;
  const html=ids.map(id=>{
    const L=LINES[id];
    const run=L.d.sim.outputs.some(s2=>effL(L,s2));
    const trip=(L.m.faults||[]).some(f=>f.type==="trip"&&L.faults[f.id]);
    const prodN=L.scene.prod?L.scene.prod(L.sst):0;
    const oee=lineOEE(L);
    const warns=L.log.filter(e=>e.lv==="warn").length;
    return `<div class="ovc${id===cur.id?" act":""}" data-id="${id}">`+
      `<div class="ovt"><span class="dot ${trip?"trip":run?"on-o":""}"></span>${OV[id]||id}</div>`+
      `<div class="ovs"><span>생산 <b>${prodN}</b></span><span>OEE <b>${oee===null?"—":Math.round(oee)+"%"}</b></span><span>경보 <b class="${warns?"w":""}">${warns}</b></span></div>`+
      (trip?'<div class="ovw">⚠ 설비 트립</div>':"")+`</div>`;
  }).join("");
  if(html!==_ovHtml){_ovHtml=html;el.innerHTML=html;}
}
document.getElementById("overview").addEventListener("click",e=>{
  const c=e.target.closest(".ovc");
  if(c&&c.dataset.id!==cur.id)show(c.dataset.id);
});

/* ---- 레시피 표시 ---- */
function ioRow(s,kind,m){
  return `<tr><td><span class="dot" id="dot_${s}"></span></td><td><b>${s}</b></td>`+
   `<td class="mut">${m.addr[s]||""}</td><td class="mut">${m.desc[s]||""}</td><td class="mut">${kind}</td></tr>`;
}
function fbRow(s,m,kind){
  return `<tr><td><span class="dot" id="dot_${s}"></span></td><td><b>${s}</b></td>`+
   `<td class="mut">${m.addr[s]||""}</td><td colspan="2"><div class="tbar"><i id="bar_${s}"></i></div>`+
   `<span class="mut" id="bt_${s}" style="font-size:11px"></span></td></tr>`;
}
function makeLine(id){
  const d=DEMO[id],m=META[id];
  const L={id,d,m,plc:makePLC(d.ladder),scene:SCENES[m.scene],scanN:0,us:0,lastKey:"",stats:{},
    kpi:{t0:performance.now(),lastN:0,lastDoneT:null,takt:null,taktAvg:null,kw:0,kwh:0},
    log:[],trend:[],lastTrendT:0,prevO:{},prevI:{},prevQ:{},taktAlarm:false,
    speedF:1,ngRate:8,demandF:1,faults:{},auto:true,apPulse:null,apCool:Math.random()*2,
    cpu:({motor_start_stop:"XGK-CPUE",fwd_rev:"FX5U-32MR/ES",car_wash:"CP1L-EM30",
      count_eject:"XBC-DR32H",conveyor_divert:"NX1P2-1140DT",weld_cell:"R04CPU",
      batch_fill_mix_drain:"CJ2M-CPU31",duty_standby:"CPU 1214C",
      cascade_conveyor:"XGK-CPUH"})[id]||"XGK-CPUH",
    devCfg:{}};
  L.sst=L.scene.init();
  d.sim.outputs.forEach(s2=>L.stats[s2]={rt:0,starts:0,prev:false});
  L.log.unshift({lv:"info",msg:"라인 투입 — "+d.title,t:"T+0.0s"});
  return L;
}
function show(id){
  if(COSIM.on&&COSIM.line!==id)cosimStop("라인 전환");
  cur=LINES[id];
  hideDev();
  const d=cur.d,m=cur.m;
  const ctrl=document.getElementById("ctrl");ctrl.innerHTML="";
  m.buttons.forEach(b=>{
    const w=document.createElement("div");w.className="pbw";
    const btn=document.createElement("button");btn.className="pb";btn.textContent=b.label;
    btn.style.background=`radial-gradient(circle at 35% 28%, ${shade(b.c,1.25)}, ${shade(b.c,0.55)})`;
    const dn=e=>{e.preventDefault();btn.classList.add("down");
      if(cur.auto){cur.auto=false;
        const ab2=document.getElementById("autob");if(ab2)ab2.classList.remove("on");
        logEv("op","수동 조작 감지 — 자동 시연 해제");}
      cur.plc.set(b.sym,true);};
    const up=()=>{btn.classList.remove("down");cur.plc.set(b.sym,false);};
    btn.addEventListener("pointerdown",dn);
    btn.addEventListener("pointerup",up);
    btn.addEventListener("pointerleave",up);
    btn.addEventListener("pointercancel",up);
    btn.addEventListener("contextmenu",e=>e.preventDefault());
    const lab=document.createElement("small");lab.textContent=`${b.sym} · ${m.addr[b.sym]}`;
    w.append(btn,lab);ctrl.appendChild(w);
  });
  const ab=document.createElement("button");
  ab.id="autob";ab.className="fbtn abtn"+(cur.auto?" on":"");ab.textContent="▶ 자동 시연";
  ab.onclick=()=>{cur.auto=!cur.auto;ab.classList.toggle("on",cur.auto);
    logEv("op","자동 시연 "+(cur.auto?"ON":"OFF"));};
  const aw=document.createElement("div");aw.className="sld";aw.appendChild(ab);
  ctrl.appendChild(aw);
  const sb=document.createElement("button");
  sb.className="fbtn abtn";sb.textContent="⚙ 설정";
  sb.onclick=()=>{document.getElementById("setwrap").style.display="block";};
  const sw2=document.createElement("div");sw2.className="sld";sw2.appendChild(sb);
  ctrl.appendChild(sw2);
  buildSettings();
  const hint=document.createElement("div");hint.className="hint";
  hint.textContent=cur.m.autoInputs
    ?"센서 입력은 라인 위 부품/수위가 실제로 만들어냅니다. 버튼을 누르면 자동 시연이 꺼지고 수동 모드가 됩니다."
    :"자동 시연이 라인을 운전 중입니다. 버튼을 누르면 즉시 수동 모드 — 자기유지는 래더가 합니다.";
  ctrl.appendChild(hint);
  document.getElementById("iotable").innerHTML=
    d.sim.inputs.map(s2=>ioRow(s2,(m.autoInputs&&m.autoInputs[s2])||"입력 P",m)).join("")+
    d.sim.outputs.map(s2=>ioRow(s2,"출력 P",m)).join("")+
    Object.keys(cur.plc.timers).map(s2=>fbRow(s2,m)).join("")+
    Object.keys(cur.plc.counters).map(s2=>fbRow(s2,m)).join("")+
    dRegs(cur).map(([addr,nm,get,unit,kind])=>
      `<tr><td><span class="dot on-i" style="background:${kind==="sp"?"#d9a514":"#7c5cff"};box-shadow:0 0 8px ${kind==="sp"?"#d9a514":"#7c5cff"}"></span></td>`+
      `<td><b>${addr}</b></td><td class="mut">${nm}</td>`+
      `<td colspan="2"><b id="an_${addr}" style="color:${kind==="sp"?"#f0c26b":"#b9a3ff"}">${get()}</b> `+
      `<span class="mut">${unit} · ${kind==="sp"?"설정 D(HMI 기록)":"데이터 D(공정 누계)"}</span></td></tr>`).join("")+
    Object.entries(m.analog||{}).map(([addr,a])=>
      `<tr><td><span class="dot on-i" style="background:#7c5cff;box-shadow:0 0 8px #7c5cff"></span></td>`+
      `<td><b>${addr}</b></td><td class="mut">${a.name}</td>`+
      `<td colspan="2"><b id="an_${addr}" style="color:#b9a3ff">—</b> <span class="mut">${a.unit} · 아날로그 D(트윈 계측)</span></td></tr>`).join("");
  document.getElementById("st").textContent=d.st;
  document.getElementById("explain").textContent=d.explain;
  document.getElementById("sim").innerHTML=tg(d.sim);
  document.getElementById("verify").innerHTML=
    `<h4>이 설계의 검증 결과 — 엔진이 출하 전 자동 수행</h4><ul>${m.verify.map(v=>`<li>${v}</li>`).join("")}</ul>`;
  document.getElementById("safety").textContent=
    "⚠️ 안전 경계: 본 검증은 로직 보조이며 기능안전 인증이 아닙니다. E-stop·가드 등 안전기능은 하드와이어 안전회로로 구현해야 합니다(ISO 13849 / IEC 62061). 3D 설비는 디지털트윈 시각화입니다.";
  cur.lastKey="";
  document.getElementById("ladder").innerHTML=ladderLive(d.ladder,null,cur.plc,m.addr);
  const wd0=document.getElementById("wiring");
  if(wd0)wd0.innerHTML=wiringSvg(cur);
  updateOverview();
  if(!rafId){resize();lastT=performance.now();rafId=requestAnimationFrame(loop);}
}
ids.forEach(id=>{LINES[id]=makeLine(id);});
show(ids[0]);

/* ---- 알람 CSV·운전 리포트 내보내기 ---- */
function dl(name,text,mime){
  const a=document.createElement("a");
  a.href=URL.createObjectURL(new Blob([text],{type:mime||"text/plain"}));
  a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),800);
}
document.getElementById("csvbtn").onclick=()=>{
  const rows=[["time","level","message"],...cur.log.slice().reverse().map(e=>[e.t,e.lv,e.msg])];
  dl(cur.id+"_alarms.csv","\uFEFF"+rows.map(r=>r.map(c=>'"'+String(c).replace(/"/g,'""')+'"').join(",")).join("\n"),"text/csv");
  logEv("op","알람 이력 CSV 내보내기");
};
document.getElementById("rptbtn").onclick=()=>{
  const L=cur,K=L.kpi,cfg=KPI[L.id]||{};
  const oee=lineOEE(L);
  const out=[
   "# 운전 리포트 — "+L.d.title,
   "생성: "+new Date().toLocaleString("ko-KR"),
   "",
   "## KPI",
   "- 생산수량: "+(L.scene.prod?L.scene.prod(L.sst):0)+" "+cfg.unit,
   "- 택타임: "+(K.taktAvg?K.taktAvg.toFixed(2)+" s (목표 "+cfg.tt+" s)":"미측정"),
   "- OEE: "+(oee===null?"미측정":oee.toFixed(0)+"%"),
   "- 누적 전력량: "+(K.kwh*1000).toFixed(1)+" Wh",
   "",
   "## 기기 운전 데이터",
   ...Object.entries(L.m.tags||{}).map(([sym,i2])=>
     "- "+i2.tag+" "+i2.name+": 가동 "+L.stats[sym].rt.toFixed(0)+"s · 기동 "+L.stats[sym].starts+"회"),
   "",
   "## 알람·이벤트 ("+L.log.length+"건)",
   ...L.log.slice().reverse().map(e=>"- ["+e.t+"]["+e.lv+"] "+e.msg),
   "",
   "## 검증 결과(엔진 자동)",
   ...L.m.verify.map(v=>"- "+v)
  ];
  dl(L.id+"_report.md",out.join("\n"),"text/markdown");
  logEv("op","운전 리포트 내보내기");
};

/* ---- 서버 코사임(정밀 모드) — API 서버에서 서빙될 때만 노출 ---- */
(function(){
  if(!/^https?:$/.test(location.protocol))return;
  const bar=document.getElementById("cosimbar");if(!bar)return;
  const b=document.createElement("button");b.className="fbtn abtn";b.id="cosimbtn";
  b.textContent="서버 코사임 ON/OFF — 10ms 정밀 스캔(브라우저 PLC 대체)";
  b.onclick=()=>{COSIM.on?cosimStop("수동 OFF"):cosimStart();};
  bar.appendChild(b);
})();
function cosimStart(){
  let ws;
  try{
    ws=new WebSocket((location.protocol==="https:"?"wss://":"ws://")+location.host+"/api/cosim");
  }catch(e){logEv("warn","코사임 연결 실패");return;}
  COSIM.ws=ws;COSIM.on=true;COSIM.ready=false;COSIM.acc=0;
  COSIM.lastSent={};COSIM.line=cur.id;COSIM.pend=0;
  document.getElementById("cosimbtn").classList.add("on");
  ws.onopen=()=>ws.send(JSON.stringify({type:"init",st_code:cur.d.st,step_ms:10}));
  ws.onmessage=ev=>{
    const m=JSON.parse(ev.data);
    if(m.type==="ready"){COSIM.ready=true;COSIM.io={inputs:m.inputs,outputs:m.outputs};
      logEv("info","서버 코사임 연결 — 10ms 스캔(OpenPLC 차분검증 코어)");
      let tb=document.getElementById("trcbtn");
      if(!tb){tb=document.createElement("button");tb.id="trcbtn";tb.className="fbtn abtn";
        tb.textContent="트레이스 리플레이 ↻";tb.style.marginLeft="6px";
        tb.onclick=()=>{if(COSIM.ws&&COSIM.ws.readyState===1)COSIM.ws.send(JSON.stringify({type:"trace"}));};
        document.getElementById("cosimbar").appendChild(tb);}}
    else if(m.type==="trace")replayTrace(m);
    else if(m.type==="state"){COSIM.pend=Math.max(0,COSIM.pend-1);applyCosim(m);}
    else if(m.type==="error")logEv("warn","코사임 오류: "+m.error);
  };
  ws.onclose=()=>{if(COSIM.on)cosimStop("연결 종료");};
}
function replayTrace(m){
  const n=m.samples.length;
  if(!n){logEv("op","트레이스 비어 있음 — 먼저 라인을 가동하세요");return;}
  const stride=Math.max(1,Math.ceil(n/120));
  const sim={inputs:COSIM.io.inputs,outputs:COSIM.io.outputs,
    samples:m.samples.filter((_,i)=>i%stride===0).map(sm=>({t:sm.t_ms,i:sm.i,o:sm.o}))};
  const det=document.querySelector("details.engd");if(det)det.open=true;
  document.getElementById("sim").innerHTML=
    `<div class="scanline" style="margin-bottom:6px"><span>서버 트레이스 <b>${n}스캔 × 10ms</b>${m.truncated?" (앞부분 절단)":""}</span>`+
    `<span><button class="xbtn" id="trcdl">JSON ↓</button></span></div>`+tg(sim);
  document.getElementById("trcdl").onclick=()=>dl(cur.id+"_trace.json",JSON.stringify(m.samples),"application/json");
  document.getElementById("sim").scrollIntoView({behavior:"smooth",block:"center"});
  logEv("info","트레이스 리플레이 — "+n+"스캔 회수(축약 표시 1/"+stride+")");
}
function cosimStop(why){
  COSIM.on=false;COSIM.ready=false;
  const tb=document.getElementById("trcbtn");if(tb)tb.remove();
  try{if(COSIM.ws)COSIM.ws.close();}catch(e){}
  COSIM.ws=null;
  const b=document.getElementById("cosimbtn");if(b)b.classList.remove("on");
  logEv("op","서버 코사임 해제("+why+") — 브라우저 PLC 폴백");
}
function applyCosim(m){
  if(!COSIM.on||COSIM.line!==cur.id)return;
  COSIM.t_ms=m.t_ms;
  const L=LINES[COSIM.line];
  for(const[sym,v]of Object.entries(m.outputs||{}))L.plc.vars[sym]=v;
  for(const[n,t2]of Object.entries(m.timers||{})){
    const lt=L.plc.timers[n];if(lt){lt.acc=t2.acc_ms/1000;lt.q=t2.q;}
  }
  for(const[n,c]of Object.entries(m.counters||{})){
    const lc=L.plc.counters[n];if(lc){lc.cnt=c.cnt;lc.q=c.q;}
  }
}
function cosimPump(L,dt){
  if(!COSIM.on||!COSIM.ready||COSIM.line!==L.id||!COSIM.ws||COSIM.ws.readyState!==1)return;
  const set={};
  for(const s2 of L.d.sim.inputs){
    const v=!!L.plc.vars[s2];
    if(COSIM.lastSent[s2]!==v){set[s2]=v;COSIM.lastSent[s2]=v;}
  }
  if(Object.keys(set).length){COSIM.ws.send(JSON.stringify({type:"set",inputs:set}));COSIM.pend++;}
  COSIM.acc+=dt*1000;
  if(COSIM.acc>=100&&COSIM.pend<4){
    const scans=Math.min(500,Math.round(COSIM.acc/10));
    COSIM.acc-=scans*10;
    COSIM.ws.send(JSON.stringify({type:"step",scans}));COSIM.pend++;
  }
}

/* ---- 평문 입력 → 키워드 매칭(엔진 nlmatch 연동) ---- */
const KW={motor_start_stop:["모터","기동","버튼","돌","멈"],
         fwd_rev:["정역","정방향","역방향","전진","후진","방향","대차"],
         car_wash:["세차","비누","헹굼","건조"],
         count_eject:["카운트","개수","세면","배출","부품","검출"],
         conveyor_divert:["비전","검사","분기","게이트","카메라","분류","불량"],
         weld_cell:["용접","클램프","로봇","지그"],
         batch_fill_mix_drain:["배치","충전","교반","혼합","탱크","드럼"],
         duty_standby:["펌프","수위","교대","리드","래그","급수","듀티"],
         cascade_conveyor:["다단","순차","컨베이어","상류","하류","적체"]};
function matchId(t){let best=ids[0],bs=0;for(const id of ids){const s=(KW[id]||[]).reduce((a,k)=>a+(t.includes(k)?1:0),0);if(s>bs){bs=s;best=id;}}return best;}
function runNL(){const t=document.getElementById("nl").value;show(matchId(t));
  document.getElementById("demo").scrollIntoView({behavior:"smooth"});}

/* ---- 예시 칩 + 타이핑 플레이스홀더 ---- */
const EX=[["버튼 누르면 모터 돌고 정지 누르면 멈추게","motor_start_stop"],
         ["부품 10개 세면 배출 실린더 작동","count_eject"],
         ["비전 검사로 불량은 B게이트 분기","conveyor_divert"],
         ["클램프 → 용접 → 해제 순서로 로봇 셀","weld_cell"],
         ["탱크에 충전하고 교반한 뒤 배출","batch_fill_mix_drain"],
         ["세차기: 비누 → 헹굼 → 건조 자동","car_wash"]];
const chips=document.getElementById("chips");
EX.forEach(([txtv,id])=>{const c=document.createElement("span");c.className="chip";c.textContent="“"+txtv+"”";
  c.onclick=()=>{document.getElementById("nl").value=txtv;show(id);document.getElementById("demo").scrollIntoView({behavior:"smooth"});};chips.appendChild(c);});
const nlEl=document.getElementById("nl");let ei=0,ci=0,del=false;
function typeFx(){const s=EX[ei][0];nlEl.setAttribute("placeholder",s.slice(0,ci)+(ci<s.length?"▋":""));
  if(!del){ci++;if(ci>s.length){del=true;return setTimeout(typeFx,1400);}}else{ci--;if(ci<=0){del=false;ei=(ei+1)%EX.length;}}
  setTimeout(typeFx,del?28:70);}
typeFx();

/* ---- 3D 파이프라인 보드: 마우스 패럴랙스 ---- */
(function(){
  const vp=document.getElementById("p3dvp"),bd=document.getElementById("p3d");
  if(!vp||!bd||!matchMedia("(pointer:fine)").matches)return;
  vp.addEventListener("pointermove",e=>{
    const r=vp.getBoundingClientRect();
    const nx=(e.clientX-r.left)/r.width-0.5, ny=(e.clientY-r.top)/r.height-0.5;
    const sc=innerWidth<1010?" scale(.8)":"";
    bd.style.transform=`rotateX(${(32-ny*11).toFixed(1)}deg) rotateZ(${(-7+nx*9).toFixed(1)}deg)`+sc;
  });
  vp.addEventListener("pointerleave",()=>{bd.style.transform="";});
})();

/* 스크롤 등장 */
const io=new IntersectionObserver(es=>es.forEach(e=>{if(e.isIntersecting)e.target.classList.add("in");}),{threshold:.12});
document.querySelectorAll(".reveal").forEach(s=>io.observe(s));

