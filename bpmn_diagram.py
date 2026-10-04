"""Реализация DIAGRAM API из ТЗ хакатона + автолейаут + экспорт BPMN 2.0 XML (с BPMNDI)."""
from xml.sax.saxutils import quoteattr

KINDS = {  # kind -> (xml tag, id prefix, size class)
    "startEvent": ("startEvent", "StartEvent", "event"),
    "endEvent": ("endEvent", "EndEvent", "event"),
    "task": ("task", "Task", "task"),
    "userTask": ("userTask", "UserTask", "task"),
    "scriptTask": ("scriptTask", "ScriptTask", "task"),
    "subProcess": ("subProcess", "SubProcess", "task"),
    "exclusiveGateway": ("exclusiveGateway", "Gateway", "gateway"),
    "parallelGateway": ("parallelGateway", "Gateway", "gateway"),
    "inclusiveGateway": ("inclusiveGateway", "Gateway", "gateway"),
}
DIMS = {"event": (36, 36), "task": (110, 80), "gateway": (50, 50)}
GAP_X, ROW_PAD, MIN_ROW = 70, 50, 110
SUB_PADX, SUB_HEAD, SUB_PADY = 30, 40, 30
LANE_X, LANE_PAD = 30, 30


class Diagram:
    ROOT_PROCESS_ID = "Process_1"
    ROOT_START_TASK_ID = "StartEvent_1"
    ROOT_END_TASK_ID = "EndEvent_1"

    def __init__(self, title="Процесс"):
        self.title = title
        self.nodes, self.edges, self.lanes, self.groups = {}, [], {}, {}
        self.pool_id = None
        self._n = 0
        self._put("startEvent", "Начало", self.ROOT_PROCESS_ID, self.ROOT_START_TASK_ID)
        self._put("endEvent", "Конец", self.ROOT_PROCESS_ID, self.ROOT_END_TASK_ID)

    # ---------- публичный API (как в ТЗ) ----------
    def create_subprocess(self, name, container): return self._put("subProcess", name, container)
    def add_task(self, name, container): return self._put("task", name, container)
    def add_user_task(self, name, container): return self._put("userTask", name, container)
    def add_script_task(self, name, container): return self._put("scriptTask", name, container)
    def add_exclusive_gateway(self, name, container): return self._put("exclusiveGateway", name, container)
    def add_parallel_gateway(self, name, container): return self._put("parallelGateway", name, container)
    def add_inclusive_gateway(self, name, container): return self._put("inclusiveGateway", name, container)

    def add_pool(self, container, lane_names):
        self._check_container(container)
        self.pool_id = self.pool_id or "Participant_1"
        ids = []
        for nm in lane_names:
            self._n += 1
            lid = f"Lane_{self._n}"
            self.lanes[lid] = str(nm)
            ids.append(lid)
        return self.pool_id, ids

    def add_group(self, name, container):
        self._check_container(container)
        self._n += 1
        gid = f"Group_{self._n}"
        self.groups[gid] = {"name": str(name), "container": container}
        return gid

    def add_link(self, parent_id, child_id, label=None):
        for x in (parent_id, child_id):
            if x not in self.nodes:
                raise ValueError(f"add_link: неизвестный узел {x!r}")
        if parent_id == child_id or any(e[0] == parent_id and e[1] == child_id for e in self.edges):
            return
        self.edges.append((parent_id, child_id, label))

    # ---------- внутреннее ----------
    def _valid_container(self, c):
        return (c == self.ROOT_PROCESS_ID or c in self.lanes or c in self.groups
                or (c in self.nodes and self.nodes[c]["kind"] == "subProcess"))

    def _check_container(self, c):
        if not self._valid_container(c):
            raise ValueError(f"Неизвестный контейнер {c!r}")

    def _put(self, kind, name, container, nid=None):
        self._check_container(container)
        self._n += 1
        nid = nid or f"{KINDS[kind][1]}_{self._n}"
        self.nodes[nid] = {"kind": kind, "name": str(name), "container": container}
        return nid

    def _resolve(self, c):
        lane, groups = None, []
        for _ in range(50):
            if c == self.ROOT_PROCESS_ID:
                return c, lane, groups
            if c in self.lanes:
                lane, c = lane or c, self.ROOT_PROCESS_ID
            elif c in self.groups:
                groups.append(c)
                c = self.groups[c]["container"]
            elif c in self.nodes and self.nodes[c]["kind"] == "subProcess":
                return c, lane, groups
            else:
                raise ValueError(f"Неизвестный контейнер {c!r}")
        raise ValueError("Слишком глубокая вложенность")

    # ---------- проверки структуры ----------
    def check(self):
        succ = {i: [] for i in self.nodes}
        pred = {i: [] for i in self.nodes}
        for a, b, _ in self.edges:
            succ[a].append(b); pred[b].append(a)

        def reach(start, adj):
            seen, st = {start}, [start]
            while st:
                for v in adj[st.pop()]:
                    if v not in seen:
                        seen.add(v); st.append(v)
            return seen
        fwd, bwd = reach(self.ROOT_START_TASK_ID, succ), reach(self.ROOT_END_TASK_ID, pred)
        out = []
        for i, n in self.nodes.items():
            if i not in fwd: out.append(f"«{n['name']}» ({i}) недостижим от ROOT_START_TASK_ID")
            elif i not in bwd: out.append(f"«{n['name']}» ({i}) не ведёт к ROOT_END_TASK_ID")
            if n["kind"].endswith("Gateway") and len(succ[i]) < 2 and len(pred[i]) < 2:
                out.append(f"Шлюз «{n['name']}» ({i}) не ветвит и не сливает потоки")
        return out

    # ---------- раскладка ----------
    def _prepare(self):
        self.info = {i: self._resolve(n["container"]) for i, n in self.nodes.items()}
        if self.lanes:
            first = next(iter(self.lanes))
            for _ in range(3):
                for i in self.nodes:
                    p, l, g = self.info[i]
                    if p != self.ROOT_PROCESS_ID or l:
                        continue
                    cand = next((self.info[a][1] for a, b, _x in self.edges if b == i and self.info[a][1]), None) \
                        or next((self.info[b][1] for a, b, _x in self.edges if a == i and self.info[b][1]), None)
                    if cand:
                        self.info[i] = (p, cand, g)
            for i, (p, l, g) in list(self.info.items()):
                if p == self.ROOT_PROCESS_ID and not l:
                    self.info[i] = (p, first, g)

    def _layout(self, p):
        ids = [i for i in self.nodes if self.info[i][0] == p]
        S = set(ids)
        size, inner = {}, {}
        for i in ids:
            k = self.nodes[i]["kind"]
            if k == "subProcess":
                inner[i] = self._layout(i)
                size[i] = (max(inner[i]["w"], 100) + 2 * SUB_PADX, max(inner[i]["h"], 60) + SUB_HEAD + SUB_PADY)
            else:
                size[i] = DIMS[KINDS[k][2]]
        succ = {i: [] for i in ids}; pred = {i: [] for i in ids}
        for a, b, _l in self.edges:
            if a in S and b in S:
                succ[a].append(b); pred[b].append(a)
        color, back, post = {}, set(), []

        def dfs(u):
            color[u] = 1
            for v in succ[u]:
                if color.get(v) == 1: back.add((u, v))
                elif v not in color: dfs(v)
            color[u] = 2; post.append(u)
        starts = [i for i in ids if not pred[i]]
        starts.sort(key=lambda i: i != self.ROOT_START_TASK_ID)
        for s in starts + ids:
            if s not in color: dfs(s)
        topo = post[::-1]
        rank = {i: 0 for i in ids}
        for u in topo:
            for v in succ[u]:
                if (u, v) not in back:
                    rank[v] = max(rank[v], rank[u] + 1)
        if self.ROOT_END_TASK_ID in S:
            rank[self.ROOT_END_TASK_ID] = max(rank.values())
        nr = (max(rank.values()) + 1) if ids else 1
        colw = [0] * nr
        for i in ids: colw[rank[i]] = max(colw[rank[i]], size[i][0])
        colx, x = [], 0
        for w in colw: colx.append(x); x += w + GAP_X
        total_w = max(x - GAP_X, 0)

        lane_of = (lambda i: self.info[i][1]) if (p == self.ROOT_PROCESS_ID and self.lanes) else (lambda i: None)
        used, slot = {}, {}
        for u in topo:
            L = lane_of(u)
            pref = next((slot[q] for q in pred[u] if (q, u) not in back and q in slot and lane_of(q) == L), 0)
            taken = used.setdefault((L, rank[u]), set())
            s = pref
            while s in taken: s += 1
            taken.add(s); slot[u] = s
        slot_h = {}
        for i in ids:
            k = (lane_of(i), slot[i])
            slot_h[k] = max(slot_h.get(k, 0), size[i][1] + ROW_PAD)
        order = list(self.lanes) if (p == self.ROOT_PROCESS_ID and self.lanes) else [None]
        geo, y = {}, 0
        for L in order:
            n = max([s for (l, s) in slot_h if l == L], default=-1) + 1 or 1
            ys, cur = {}, y
            for s in range(n):
                h = slot_h.get((L, s), MIN_ROW); ys[s] = (cur, h); cur += h
            geo[L] = (y, cur - y, ys); y = cur
        pos = {}
        for i in ids:
            sy, sh = geo[lane_of(i)][2][slot[i]]
            w, h = size[i]
            pos[i] = (colx[rank[i]] + (colw[rank[i]] - w) / 2, sy + (sh - h) / 2, w, h)
        return {"pos": pos, "w": total_w, "h": y, "geo": geo, "inner": inner}

    def _place(self, lay, ox, oy):
        for i, (x, y, w, h) in lay["pos"].items():
            self.abs[i] = (ox + x, oy + y, w, h)
            if i in lay["inner"]:
                self._place(lay["inner"][i], ox + x + SUB_PADX, oy + y + SUB_HEAD)

    def _waypoints(self, a, b):
        ax, ay, aw, ah = self.abs[a]; bx, by, bw, bh = self.abs[b]
        acy, bcy = ay + ah / 2, by + bh / 2
        if bx >= ax + aw:
            if abs(acy - bcy) < 1: return [(ax + aw, acy), (bx, bcy)]
            mx = (ax + aw + bx) / 2
            return [(ax + aw, acy), (mx, acy), (mx, bcy), (bx, bcy)]
        yb = max(ay + ah, by + bh) + 30
        acx, bcx = ax + aw / 2, bx + bw / 2
        return [(acx, ay + ah), (acx, yb), (bcx, yb), (bcx, by + bh)]

    # ---------- экспорт ----------
    def _emit_flow(self, p, ind, out):
        pad = " " * ind
        eid = {(a, b): f"Flow_{k + 1}" for k, (a, b, _l) in enumerate(self.edges)}
        for nid, n in self.nodes.items():
            if self.info[nid][0] != p: continue
            tag = KINDS[n["kind"]][0]
            name = f" name={quoteattr(n['name'])}" if n["name"] else ""
            extra = ""
            io = "".join(f"\n{pad}    <bpmn:incoming>{eid[(a, b)]}</bpmn:incoming>" for a, b, _l in self.edges if b == nid)
            io += "".join(f"\n{pad}    <bpmn:outgoing>{eid[(a, b)]}</bpmn:outgoing>" for a, b, _l in self.edges if a == nid)
            if n["kind"] == "subProcess":
                out.append(f'{pad}  <bpmn:subProcess id="{nid}"{name}>{io}')
                self._emit_flow(nid, ind + 4, out)
                out.append(f"{pad}  </bpmn:subProcess>")
            else:
                out.append(f'{pad}  <bpmn:{tag} id="{nid}"{name}{extra}>{io}\n{pad}  </bpmn:{tag}>' if io
                           else f'{pad}  <bpmn:{tag} id="{nid}"{name}{extra} />')
        for k, (a, b, lab) in enumerate(self.edges):
            owner = self.info[a][0] if self.info[a][0] == self.info[b][0] else self.ROOT_PROCESS_ID
            if owner == p:
                ln = f" name={quoteattr(lab)}" if lab else ""
                out.append(f'{pad}  <bpmn:sequenceFlow id="Flow_{k + 1}"{ln} sourceRef="{a}" targetRef="{b}" />')

    def to_xml(self):
        self._prepare()
        lay = self._layout(self.ROOT_PROCESS_ID)
        self.abs = {}
        has_lanes = bool(self.lanes)
        ox, oy = (LANE_X + LANE_PAD, 0) if has_lanes else (30, 30)
        self._place(lay, ox, oy)

        members = {g: [i for i in self.nodes if g in self.info[i][2]] for g in self.groups}
        live_groups = {g: m for g, m in members.items() if m}
        x = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" '
             'xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI" '
             'xmlns:dc="http://www.omg.org/spec/DD/20100524/DC" '
             'xmlns:di="http://www.omg.org/spec/DD/20100524/DI" '
             'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
             'id="Definitions_1" targetNamespace="http://bpmn.io/schema/bpmn" '
             'exporter="bpmn-ai-assistant" exporterVersion="1.0">']
        for g in live_groups:
            x.append(f'  <bpmn:category id="Category_{g}"><bpmn:categoryValue id="CatVal_{g}" '
                     f'value={quoteattr(self.groups[g]["name"])} /></bpmn:category>')
        if has_lanes:
            x += ['  <bpmn:collaboration id="Collaboration_1">',
                  f'    <bpmn:participant id="{self.pool_id}" name={quoteattr(self.title)} processRef="{self.ROOT_PROCESS_ID}" />',
                  '  </bpmn:collaboration>']
        x.append(f'  <bpmn:process id="{self.ROOT_PROCESS_ID}" isExecutable="false">')
        if has_lanes:
            x.append('    <bpmn:laneSet id="LaneSet_1">')
            for lid, nm in self.lanes.items():
                x.append(f'      <bpmn:lane id="{lid}" name={quoteattr(nm)}>')
                for i in self.nodes:
                    if self.info[i][0] == self.ROOT_PROCESS_ID and self.info[i][1] == lid:
                        x.append(f"        <bpmn:flowNodeRef>{i}</bpmn:flowNodeRef>")
                x.append("      </bpmn:lane>")
            x.append("    </bpmn:laneSet>")
        self._emit_flow(self.ROOT_PROCESS_ID, 2, x)
        for g in live_groups:
            x.append(f'    <bpmn:group id="{g}" categoryValueRef="CatVal_{g}" />')
        x.append("  </bpmn:process>")

        plane = "Collaboration_1" if has_lanes else self.ROOT_PROCESS_ID
        x += ['  <bpmndi:BPMNDiagram id="BPMNDiagram_1">', f'    <bpmndi:BPMNPlane id="BPMNPlane_1" bpmnElement="{plane}">']

        def shape(eid, bx, by, bw, bh, attrs="", label=None):
            s = f'      <bpmndi:BPMNShape id="{eid}_di" bpmnElement="{eid}"{attrs}>\n' \
                f'        <dc:Bounds x="{bx:.0f}" y="{by:.0f}" width="{bw:.0f}" height="{bh:.0f}" />'
            if label:
                s += f'\n        <bpmndi:BPMNLabel><dc:Bounds x="{label[0]:.0f}" y="{label[1]:.0f}" width="{label[2]:.0f}" height="{label[3]:.0f}" /></bpmndi:BPMNLabel>'
            x.append(s + "\n      </bpmndi:BPMNShape>")
        if has_lanes:
            shape(self.pool_id, 0, 0, lay["w"] + 2 * LANE_PAD + LANE_X, lay["h"], ' isHorizontal="true"')
            for lid in self.lanes:
                top, h, _ys = lay["geo"][lid]
                shape(lid, LANE_X, top, lay["w"] + 2 * LANE_PAD, h, ' isHorizontal="true"')
        for g, m in live_groups.items():
            bx = min(self.abs[i][0] for i in m) - 20; by = min(self.abs[i][1] for i in m) - 20
            ex = max(self.abs[i][0] + self.abs[i][2] for i in m) + 20; ey = max(self.abs[i][1] + self.abs[i][3] for i in m) + 20
            shape(g, bx, by, ex - bx, ey - by)
        for i, n in self.nodes.items():
            bx, by, bw, bh = self.abs[i]
            attrs, label = "", None
            k = n["kind"]
            if k == "subProcess": attrs = ' isExpanded="true"'
            if k == "exclusiveGateway": attrs = ' isMarkerVisible="true"'
            if KINDS[k][2] in ("event", "gateway") and n["name"]:
                label = (bx + bw / 2 - 50, by + bh + 4, 100, 27)
            shape(i, bx, by, bw, bh, attrs, label)
        for k, (a, b, lab) in enumerate(self.edges):
            x.append(f'      <bpmndi:BPMNEdge id="Flow_{k + 1}_di" bpmnElement="Flow_{k + 1}">')
            for px, py in self._waypoints(a, b):
                x.append(f'        <di:waypoint x="{px:.0f}" y="{py:.0f}" />')
            x.append("      </bpmndi:BPMNEdge>")
        x += ["    </bpmndi:BPMNPlane>", "  </bpmndi:BPMNDiagram>", "</bpmn:definitions>"]
        return "\n".join(x)
