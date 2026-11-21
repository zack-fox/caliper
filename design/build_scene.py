"""生成 Caliper v2.0 界面与工作流白板场景（.excalidraw），严格符合任务主题样式。"""
from __future__ import annotations
import json, random

OUT = "/tmp/caliper-wb/caliper-ui.excalidraw"

# 任务主题允许色板
BG="#F4F6F9"; INK="#111A27"; MUTED="#48566B"; LINE="#D6DCE6"
WHITE="#FFFFFF"; CARD="#FAFAFA"
PRIMARY="#1F5EFF"; PRI_SOFT="#EAF0FF"; PRI_INK="#12409E"
PURPLE="#7A3FF0"
NAVY="#131D2B"; NAVY_INK="#C3CDDD"; NAVY_MUTED="#8FA2BB"; NAVY_BORDER="#2A384B"
OK="#12A76A"; WARN="#D98300"; BAD="#D94040"
NEUTRAL_STROKE="#7373735C"   # node.neutral.stroke
SECONDARY_STROKE="#7373732E" # node.secondary.stroke

def stroke_for(fill):
    f = fill.upper()
    if f == WHITE: return NEUTRAL_STROKE
    if f == CARD: return SECONDARY_STROKE
    if f == PRIMARY: return PRIMARY
    if f == PRI_SOFT: return PRIMARY
    if f == NAVY: return NAVY_BORDER
    if f in (OK, WARN, BAD, PURPLE, MUTED, PRI_INK, NAVY_INK, NAVY_MUTED, NAVY_BORDER):
        return fill
    return NEUTRAL_STROKE

random.seed(7)
E=[]; _c=[0]
def nid(p): _c[0]+=1; return f"{p}{_c[0]}"
def _sd(): return random.randint(1,2_000_000_000)

def rect(x,y,w,h,*,fill=WHITE,stroke=None,sw=1,rounds=10,ss="solid",opacity=100):
    if stroke is None: stroke = stroke_for(fill)
    return {"id":nid("r"),"type":"rectangle","x":x,"y":y,"width":w,"height":h,"angle":0,
      "strokeColor":stroke,"backgroundColor":fill,"fillStyle":"solid",
      "strokeWidth":sw,"strokeStyle":ss,"roughness":0,"opacity":opacity,
      "groupIds":[],"frameId":None,
      "roundness":None if rounds is None else {"type":3,"value":rounds},
      "seed":_sd(),"version":1,"versionNonce":_sd(),"isDeleted":False,
      "boundElements":None,"updated":1,"link":None,"locked":False}

def text(x,y,s,*,size=16,color=INK):
    """左对齐自由文本；size 仅限 16/20/28。"""
    assert size in (16,20,28), size
    cjk=sum(1 for ch in s if ord(ch)>0x2E80); asc=len(s)-cjk
    w=int(cjk*size*1.0+asc*size*0.55)+12; h=int(size*1.5)+6
    return {"id":nid("t"),"type":"text","x":x,"y":y,"width":w,"height":h,"angle":0,
      "strokeColor":color,"backgroundColor":"transparent","fillStyle":"solid",
      "strokeWidth":1,"strokeStyle":"solid","roughness":0,"opacity":100,
      "groupIds":[],"frameId":None,"roundness":None,
      "seed":_sd(),"version":1,"versionNonce":_sd(),"isDeleted":False,
      "boundElements":None,"updated":1,"link":None,"locked":False,
      "text":s,"fontSize":size,"fontFamily":2,"textAlign":"left",
      "verticalAlign":"top","containerId":None,"originalText":s,
      "autoResize":True,"lineHeight":1.25}

def arrow(x1,y1,x2,y2,*,stroke=LINE):
    return {"id":nid("a"),"type":"arrow","x":x1,"y":y1,"width":abs(x2-x1),"height":abs(y2-y1),
      "angle":0,"strokeColor":stroke,"backgroundColor":"transparent","fillStyle":"solid",
      "strokeWidth":1,"strokeStyle":"solid","roughness":0,"opacity":100,
      "groupIds":[],"frameId":None,"roundness":None,
      "seed":_sd(),"version":1,"versionNonce":_sd(),"isDeleted":False,
      "boundElements":None,"updated":1,"link":None,"locked":False,
      "points":[[0,0],[x2-x1,y2-y1]],"lastCommittedPoint":None,
      "startBinding":None,"endBinding":None,"startArrowhead":None,
      "endArrowhead":"triangle","elbowed":False}

def swatch(x,y,label,col):
    textcol = WHITE if col in (PRIMARY,PURPLE,NAVY,BAD,PRI_INK) else INK
    return [rect(x,y,34,22,fill=col,rounds=4),
            rect(x+42,y,170,22,fill=WHITE,rounds=4),
            text(x+50,y+3,f"{label}  {col}",size=16,color=textcol if False else INK)]

# ============ 标题 ============
E.append(text(80,52,"Caliper v2.0 · 桌面端界面与工作流",size=28,color=INK))
E.append(text(80,96,"融合《前端布局原型》视觉语言 + JSecProbe 生命周期  ·  审核通过后进入基座实现",size=16,color=MUTED))

# ============ ① 应用外壳 ============
E.append(text(80,144,"① 应用外壳 · 五区结构（深色顶栏 + 深色侧栏）",size=20,color=INK))
E.append(rect(80,180,700,340,fill=BG,rounds=12))
# topbar
E.append(rect(80,180,700,60,fill=NAVY,rounds=None))
E.append(text(96,200,"顶栏 · 项目上下文：项目编号 / 名称 / 等保级别 / 范围 / AI 开关 / 头像",size=16,color=NAVY_INK))
# sidebar
E.append(rect(80,240,208,220,fill=NAVY,rounds=None))
E.append(text(96,250,"侧栏导航（分组）",size=16,color=NAVY_MUTED))
navs=[("工作流",None),("证据与资产",True),("结果记录",False),("问题与重大",False),
      ("导出与设置",False),("规则",None),("规则库",False)]
yy=280
for name,active in navs:
    if active is None:
        E.append(text(96,yy,name,size=16,color=NAVY_MUTED)); yy+=30; continue
    fill=NAVY_BORDER if active else NAVY
    E.append(rect(92,yy,184,28,fill=fill,rounds=6))
    E.append(text(104,yy+5,name,size=16,color=(PRIMARY if active else NAVY_INK)))
    yy+=36
E.append(text(96,442,"底栏：pack · 等级 · 控制项数",size=16,color=NAVY_MUTED))
# main content
E.append(rect(288,240,384,220,fill=BG,rounds=None))
E.append(text(304,252,"主内容区 · 当前视图",size=16,color=MUTED))
E.append(rect(304,280,176,84,fill=WHITE,rounds=8))
E.append(text(320,316,"上传区 / 卡片",size=16,color=MUTED))
E.append(rect(492,280,164,84,fill=WHITE,rounds=8))
E.append(text(508,316,"字段卡 / 表格",size=16,color=MUTED))
E.append(rect(304,376,352,72,fill=CARD,rounds=8))
E.append(text(320,408,"三栏工作台 / 详情面板",size=16,color=MUTED))
# AI drawer
E.append(rect(600,240,180,220,fill=WHITE,rounds=10))
E.append(text(616,252,"AI 助手抽屉",size=16,color=PURPLE))
E.append(text(616,282,"· 仅写文案字段",size=16,color=MUTED))
E.append(text(616,310,"· 不改判定 / 符合情况",size=16,color=MUTED))
E.append(text(616,338,"· 首版不接模型",size=16,color=MUTED))
E.append(text(616,420,"状态：规划中（预留接口）",size=16,color=PURPLE))
# status bar
E.append(rect(80,460,700,40,fill=CARD,rounds=None))
E.append(text(96,472,"状态栏  PROJECT · PKG · 解析进度 · AI 状态 · 版本",size=16,color=MUTED))

# ============ ② 配色令牌 ============
E.append(text(812,144,"② 配色与设计令牌",size=20,color=INK))
sw=[("主色 primary",PRIMARY),("AI 紫 series",PURPLE),("深蓝 chrome",NAVY),
    ("chrome 文字",NAVY_INK),("chrome 次文",NAVY_MUTED),
    ("成功 ok",OK),("警告 warn",WARN),("危险 bad",BAD),
    ("底色 bg",BG),("面板 surface",WHITE),("次卡片",CARD),
    ("线 line",LINE),("主文 ink",INK),("次文 muted",MUTED),
    ("主色软底",PRI_SOFT),("主色深文",PRI_INK)]
yy=184
for lab,col in sw:
    E += swatch(812,yy,lab,col); yy+=30

# ============ ③ 五步工作流 ============
E.append(text(80,556,"③ 五步工作流（侧栏主导航，箭头为推荐顺序）",size=20,color=INK))
screens=[
 ("1 证据与资产",["· 拖入即解析（离线）","· 自动提取字段卡：auto / 人工 / 待补","· 与资产记录表核对"]),
 ("2 结果记录",["· 三栏工作台（核心）","控件树 / 详情 / 判定","· 证据行号可回溯"]),
 ("3 问题与重大",["· 不符合 → 自动生成问题","· 重大隐患三性分析","· 右侧面板可编辑"]),
 ("4 导出与设置",["· 四张表导出 xlsx","· 主题 / AI / 路径设置","· 日志面板"]),
 ("5 规则库",["· 检查项 → 控制项映射","· 规则包可整体替换","· 框架不改"]),
]
cw,gap,x0=208,22,80
centers=[]
for i,(title,body) in enumerate(screens):
    x=x0+i*(cw+gap); centers.append(x+cw/2)
    E.append(rect(x,586,cw,158,fill=WHITE,rounds=10))
    E.append(rect(x,586,cw,38,fill=PRIMARY,rounds=None))
    E.append(text(x+14,596,title,size=16,color=WHITE))
    yy=636
    for b in body:
        E.append(text(x+14,yy,b,size=16,color=MUTED)); yy+=30
for i in range(len(centers)-1):
    E.append(arrow(centers[i]+cw/2,665,centers[i+1]-cw/2,665,stroke=PRIMARY))
# mini layouts
my=766; mh=78
# 1
E.append(rect(x0,my,96,mh,fill=PRI_SOFT,rounds=8)); E.append(text(x0+12,my+28,"上传区",size=16,color=PRI_INK))
E.append(rect(x0+104,my,96,mh,fill=WHITE,rounds=8)); E.append(text(x0+116,my+28,"字段卡",size=16,color=MUTED))
# 2
bx=x0+1*(cw+gap)
for j,w in enumerate((60,88,56)):
    E.append(rect(bx+j*64,my,w,mh,fill=[CARD,WHITE,CARD][j],rounds=6))
E.append(text(bx+14,my+28,"树",size=16,color=MUTED))
E.append(text(bx+86,my+28,"详情",size=16,color=MUTED))
E.append(text(bx+158,my+28,"判定",size=16,color=MUTED))
# 3
cx=x0+2*(cw+gap)
E.append(rect(cx,my,120,mh,fill=WHITE,rounds=8)); E.append(text(cx+14,my+28,"问题表",size=16,color=MUTED))
E.append(rect(cx+128,my,76,mh,fill=CARD,rounds=8)); E.append(text(cx+140,my+28,"编辑",size=16,color=MUTED))
# 4
dx=x0+3*(cw+gap)
for j in range(4):
    E.append(rect(dx+(j%2)*100,my+(j//2)*36,92,32,fill=WHITE,rounds=6))
E.append(text(dx+14,my+28,"导出卡",size=16,color=MUTED))
# 5
ex=x0+4*(cw+gap)
E.append(rect(ex,my,208,mh,fill=WHITE,rounds=8)); E.append(text(ex+14,my+28,"检查项 → 控制项 映射",size=16,color=MUTED))

# ============ ④ 核心工作台三栏 ============
E.append(text(80,880,"④ 核心工作台 · 结果记录（三栏布局 · 核查主场景）",size=20,color=INK))
E.append(rect(80,912,1020,360,fill=WHITE,rounds=12))
# left tree
E.append(rect(80,912,214,360,fill=CARD,rounds=None))
E.append(text(96,924,"控件点树（按安全域）",size=16,color=INK))
cps=[("身份鉴别",OK),("访问控制",WARN),("安全审计",OK),("入侵防范",BAD),
     ("恶意代码防范",BAD),("可信验证",BAD),("数据完整性",WARN),("数据保密性",OK),
     ("数据备份恢复",WARN),("剩余信息保护",OK),("个人信息保护",None)]
yy=952
for name,v in cps:
    dot=v if v else MUTED
    E.append(rect(96,yy+2,12,12,fill=dot,rounds=2))
    E.append(text(116,yy,name,size=16,color=INK)); yy+=28
# middle detail
E.append(rect(294,912,506,360,fill=WHITE,rounds=None))
E.append(text(310,924,"测评项详情",size=16,color=INK))
E.append(text(310,954,"d）应采用口令、密码技术、生物技术等两种或两种以上组合的鉴别技术…",size=16,color=INK))
E.append(text(310,984,"核查方法：1) 是否两种以上；2) 其一是否密码技术",size=16,color=MUTED))
E.append(text(310,1012,"判定标准：仅用户名+口令 → 不符合",size=16,color=MUTED))
E.append(rect(310,1040,474,140,fill=NAVY,rounds=8))
E.append(text(322,1050,"证据 · session.log（行号可回溯）",size=16,color=NAVY_MUTED))
E.append(text(322,1078,"[10] Password complexity  grep pam_pwquality ...",size=16,color=NAVY_INK))
E.append(text(322,1104,"  no faillock config   ← 高亮",size=16,color=WARN))
E.append(text(322,1130,"[11] Login failure lockout  grep faillock ...",size=16,color=NAVY_INK))
E.append(text(322,1156,"  ops ALL=(ALL) NOPASSWD: ALL   ← 高亮",size=16,color=WARN))
E.append(text(310,1196,"结果记录：未采用两种以上组合鉴别，仅用户名+口令。",size=16,color=INK))
# right verdict
E.append(rect(800,912,300,360,fill=CARD,rounds=None))
E.append(text(816,924,"符合性判定",size=16,color=INK))
vbtns=[("符合",OK),("部分符合",WARN),("不符合",BAD),("不适用",MUTED)]
for i,(t,c) in enumerate(vbtns):
    bx=816+(i%2)*140; by=954+(i//2)*44
    E.append(rect(bx,by,128,36,fill=WHITE,rounds=6))
    E.append(text(bx+14,by+8,t,size=16,color=c))
E.append(text(816,1060,"核查说明 / 备注（可人工修正）",size=16,color=INK))
E.append(rect(816,1086,268,80,fill=WHITE,rounds=8))
E.append(text(826,1096,"中间件无独立管理入口，鉴别由操作系统承载…",size=16,color=MUTED))
E.append(text(816,1184,"重大隐患确认",size=16,color=INK))
E.append(rect(816,1210,120,34,fill=PRI_SOFT,rounds=6))
E.append(text(830,1218,"触发判例",size=16,color=PRI_INK))
E.append(rect(948,1210,120,34,fill=WHITE,rounds=6))
E.append(text(962,1218,"不构成",size=16,color=MUTED))

# ============ ⑤ 待审核决策 ============
E.append(text(80,1304,"⑤ 待审核决策（请批注或回复，确认后进入实现）",size=20,color=INK))
qs=[
 ("Q1 · 是否保留「项目列表」？","原型定位单系统单设备核对；JSecProbe 是全生命周期项目制。基座是否需要项目管理模块？"),
 ("Q2 · 核对范围：单设备 / 多设备批量？","原型一次核对一台设备生成单张结果记录；现有 core 支持 project.yaml 多资产批量。先做哪种？"),
 ("Q3 · AI 抽屉首版是否启用？","原型预留 AI 仅写文案字段、不改判定，首版不接模型（noop 适配器）。是否先留 UI 占位？"),
 ("Q4 · 证据上传与规则包入口","原型把规则包放侧栏底部信息、上传区在首屏；规则包/输出目录是否仍放「设置」？"),
]
qw,gap=496,28
for i,(t,d) in enumerate(qs):
    x=80+(i%2)*(qw+gap); y=1340+(i//2)*118
    E.append(rect(x,y,qw,100,fill=WHITE,rounds=10))
    # 顶部紫色细条（语义填充）标识「待决策」
    E.append(rect(x,y,qw,8,fill=PURPLE,rounds=None))
    E.append(text(x+16,y+18,t,size=16,color=PURPLE))
    E.append(text(x+16,y+50,d,size=16,color=MUTED))

scene={"type":"excalidraw","version":2,"source":"https://excalidraw.com","elements":E,
 "appState":{"viewBackgroundColor":BG,"gridSize":None,
   "currentItemStrokeColor":INK,"currentItemBackgroundColor":WHITE,"currentItemFillStyle":"solid",
   "currentItemStrokeWidth":1,"currentItemStrokeStyle":"solid","currentItemRoughness":0,
   "currentItemOpacity":100,"currentItemFontFamily":2,"currentItemFontSize":16,
   "currentItemTextAlign":"left","currentItemVerticalAlign":"top",
   "currentItemStartArrowhead":None,"currentItemEndArrowhead":"triangle",
   "currentItemRoundness":"round","colorPalette":{}},"files":{}}
with open(OUT,"w",encoding="utf-8") as f: json.dump(scene,f,ensure_ascii=False)
print("wrote",OUT,"elements:",len(E))
