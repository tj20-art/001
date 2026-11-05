"""Build the final coursework report from preserved measured evidence only."""
import csv
import hashlib
import html
import json
import math
import statistics
from datetime import datetime, timezone, timedelta
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from docx import Document
from docx.shared import Cm, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

ROOT=Path(__file__).resolve().parents[1]
SOURCE=Path('D:/学习/综设3/89周-JMeter')
PAIR=SOURCE/'完整测试结果-20261105-013809'
RETEST=SOURCE/'优化后复测结果-20261105-103455'
OUT=ROOT/'performance/reports/性能测试总报告-20261105'
TZ=timezone(timedelta(hours=8))
NAME='安全电商系统性能测试总报告'
KEYS=['login','query','order']
NAMES={'login':'登录','query':'商品查询','order':'下单'}
STAGES={'before':'优化前','after':'优化后','retest':'独立复测'}
LABELS={'login':'01_普通用户登录','query':'02_商品查询','order':'03_创建订单'}

def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def fmt(v):return f'{v:.2f}'
def clock(ms):return datetime.fromtimestamp(ms/1000,TZ).strftime('%H:%M:%S.%f')[:-3]

def audit():
    pair=read(PAIR/'summary.json');retest=read(RETEST/'summary.json')
    assert pair['status']==retest['status']=='complete'
    assert pair['original_database_unchanged'] and retest['original_database_unchanged']
    assert retest['same_as_previous_optimized_source'] and retest['same_as_previous_seed']
    sources={}
    for folder in [PAIR,RETEST]:
        for name,value in read(folder/'sha256-manifest.json').items():
            assert sha(folder/name)==value,(folder,name)
        sources[str(folder/'summary.json')]=sha(folder/'summary.json')
    runs={}
    for stage,group in [('before',[r for r in pair['runs'] if r['version']=='before']),('after',[r for r in pair['runs'] if r['version']=='after']),('retest',retest['runs'])]:
        for run in group:
            key=run['scenario'];folder=(RETEST/key if stage=='retest' else PAIR/stage/key)
            with (folder/'raw.jtl').open(encoding='utf-8-sig',newline='') as f:raw=list(csv.DictReader(f))
            with (folder/'measurement.jtl').open(encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
            m=run['measurement'];latencies=sorted(int(r['elapsed']) for r in rows)
            assert len(rows)==m['samples'] and len(raw)==run['raw_http_samples']
            assert run['valid_fixed_load'] and run['window_end_ms']-run['window_start_ms']==300000
            assert all(r['label']==LABELS[key] and run['window_start_ms']<=int(r['timeStamp'])<run['window_end_ms'] for r in rows)
            assert len({r['threadName'] for r in rows})==9
            assert all(r['distinct_threads']==9 and r['min_grp_threads']==9 for r in run['coverage_30seconds'])
            assert all(r['success'].lower()=='true' for r in raw)
            assert latencies[math.ceil(len(rows)*.95)-1]==m['p95_ms']
            assert latencies[math.ceil(len(rows)*.99)-1]==m['p99_ms']
            assert abs(statistics.mean(latencies)-m['average_ms'])<1e-8
            assert abs(len(rows)/300-m['throughput_rps_fixed_window'])<1e-10
            if key=='order':assert run['order_accounting_matches']
            run=dict(run,stage=stage,evidence=str(folder.relative_to(SOURCE)))
            runs[stage,key]=run
            sources[str(folder/'measurement.jtl')]=sha(folder/'measurement.jtl')
    return pair,retest,runs,sources

def chart(runs):
    im=Image.new('RGB',(1600,650),'white');d=ImageDraw.Draw(im)
    font=lambda n:ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',n)
    colors={'before':'#a7b0be','after':'#087f8c','retest':'#3056b0'}
    x0=270;ww=1120
    d.text((0,0),'P95占固定基线的比例  越低越好',font=font(33),fill='#182233')
    for i,s in enumerate(['before','after','retest']):
        x=600+i*260;d.rectangle((x,10,x+25,34),fill=colors[s]);d.text((x+38,1),STAGES[s],font=font(27),fill='#253246')
    for pct in [0,20,40,60,80,100]:
        x=x0+ww*pct/100;d.line((x,85,x,570),fill='#e5e9ee',width=2)
        d.text((x-20,580),f'{pct}%',font=font(23),fill='#657083')
    limit=x0+ww*.8;d.line((limit,80,limit,570),fill='#ae3a32',width=3)
    d.text((limit-100,610),'80%为下降20%的界线',font=font(21),fill='#9a332c')
    for i,key in enumerate(KEYS):
        y=100+i*160;d.text((0,y+38),NAMES[key],font=font(31),fill='#182233')
        before=runs['before',key]['measurement']['p95_ms']
        for j,stage in enumerate(['before','after','retest']):
            value=runs[stage,key]['measurement']['p95_ms'];ratio=value/before*100;yy=y+j*42
            end=x0+ww*ratio/100;d.rectangle((x0,yy,end,yy+29),fill=colors[stage])
            d.text((end+12,yy-3),f'{ratio:.1f}%',font=font(24),fill='#253246')
    im.save(OUT/'P95优化对比.png')

def build():
    pair,retest,runs,sources=audit();OUT.mkdir(parents=True,exist_ok=True)
    chart(runs)
    blocks=[]
    def title(t):blocks.append(('title',t))
    def h(t):blocks.append(('h',t))
    def p(t):blocks.append(('p',t))
    def note(t):blocks.append(('note',t))
    def table(headers,rows,widths=None):blocks.append(('table',headers,rows,widths))
    def page():blocks.append(('page',))
    def image():blocks.append(('image','P95优化对比.png'))
    total=sum(r['measurement']['samples'] for r in runs.values())
    rawtotal=sum(r['raw_http_samples'] for r in runs.values())
    title(NAME)
    note('第8周性能基线与第9周系统优化  |  测试日期 2026年11月5日  |  Asia/Shanghai')
    h('测试结论')
    p('在固定9个独立账号、相同数据快照和请求间隔下，登录、商品查询、下单均完成300秒正式性能采样。同条件优化前后P95分别下降58.05%、22.22%、81.40%，三个场景错误率均为0%，满足本次对照的P95下降不少于20%及错误率不高于1%的性能指标。')
    rows=[]
    for key in KEYS:
        b,a,t=[runs[s,key]['measurement'] for s in ['before','after','retest']]
        rows.append([NAMES[key],b['p95_ms'],a['p95_ms'],f"{(1-a['p95_ms']/b['p95_ms'])*100:.2f}%",t['p95_ms'],'0%'])
    table(['场景','前P95\nms','后P95\nms','下降比例','复测P95\nms','错误率'],rows,[2.8,2.2,2.2,2.6,2.6,2.2])
    image()
    p('独立复测仍为0%错误：登录83ms、商品查询7ms、下单20ms。下单P95较上次16ms回升25%，但较固定基线86ms仍下降76.74%。复测是重复性证据，不视作新的优化收益。')
    note(f'共核对9个正式窗口、{total:,}个正式业务样本和{rawtotal:,}个全程HTTP样本。原业务数据库未改动，所有下单均在隔离副本执行，未执行支付。')
    page()
    h('测试范围与环境')
    table(['项目','配置与范围'],[
        ['机器','Windows build 26300；AMD Ryzen 7 7840H；16逻辑处理器；约15.2GiB物理内存'],
        ['运行环境','Python 3.11.5；Flask 1.1.4；MySQL 8.0.43；JMeter 5.6.3；JBR 21.0.7'],
        ['优化前服务','Werkzeug 1.0.1 HTTP/1.0，threaded，HTTPS'],
        ['优化后服务','Cheroot 11.1.2 HTTP/1.1；16个工作线程；持久连接；HTTPS'],
        ['数据与账号','原始快照13个账号、7个商品、105个订单；其中9个独立普通用户参与；测试商品ID为3，初始库存15541件'],
        ['隔离与限流','副本库按场景恢复；隔离端口24433；PERF_TEST_MODE=1，两版阈值相同；默认业务限流保持原值'],
    ],[3.1,13.5])
    h('业务脚本与断言')
    table(['场景','实际请求与验证'],[
        ['登录','POST /api/v1/auth/login；multipart提交certificate与password；校验code=0并提取access_token。每个线程固定账号，循环登录。'],
        ['商品查询','初始化登录一次，随后GET /api/v1/products循环查询商品列表；校验code=0及data.product_list存在。未按单个product_id过滤，也未测试前端页面渲染。'],
        ['下单','初始化登录、获取隧道公钥、检查空购物车；循环加购商品3数量1，再POST /api/v1/orders创建订单；请求与响应使用SM2及SM4-GCM；校验业务成功。'],
    ],[3.1,13.5])
    h('负载与统计口径')
    p('三个场景顺序执行。每场景每版9线程、9秒升压、运行390秒；以首个HTTP样本为锚点跳过70秒，统计随后连续300秒内开始的目标业务请求，余下约20秒用于收尾。每30秒核对9个线程持续参与，失败请求保留。登录等待1000ms，查询500ms，加购与下单各500ms。')
    p('P95、P99采用nearest-rank：将响应耗时升序排列，取向上取整的95%或99%位置。吞吐量为正式目标业务样本数除以300秒。错误率同时覆盖HTTP失败与业务断言失败。初始化、加购与其他标签不混入下单P95，计时不包含前置加密及后置解密脚本的执行开销。')
    note('两版机器、Python、MySQL、数据初态、账号、脚本和等待时间一致。HTTP服务器和连接复用配置是明确的优化变量，报告评价整组优化的端到端效果。')
    page()
    h('优化前后与独立复测完整指标')
    metrics=[];matrix=[]
    for key in KEYS:
        for stage in ['before','after','retest']:
            r=runs[stage,key];m=r['measurement']
            metrics.append({'场景':NAMES[key],'阶段':STAGES[stage],'用户数':9,'统计秒数':300,'样本数':m['samples'],'平均毫秒':m['average_ms'],'P95毫秒':m['p95_ms'],'P99毫秒':m['p99_ms'],'错误率百分比':m['error_percent'],'每秒请求':m['throughput_rps_fixed_window']})
            matrix.append([NAMES[key],STAGES[stage],m['samples'],fmt(m['average_ms']),m['p95_ms'],m['p99_ms'],fmt(m['throughput_rps_fixed_window']),'0%'])
    table(['场景','阶段','样本','平均ms','P95ms','P99ms','请求/s','错误率'],matrix,[2.3,2.4,1.8,2.1,1.9,1.9,2.2,2.0])
    note('登录和查询成功响应为200，下单为201。全部9个正式窗口及全程HTTP样本均无失败；吞吐量按固定300秒窗口计算，可能与JMeter按首末样本跨度计算的数值略有差异。')
    h('正式采样时间与持续负载证据')
    table(['场景','阶段','起始时间','结束时间','持续秒数'],[
        [NAMES[k],STAGES[s],clock(runs[s,k]['window_start_ms']),clock(runs[s,k]['window_end_ms']),'300']
        for k in KEYS for s in ['before','after','retest']
    ],[2.6,2.6,4.3,4.3,2.8])
    p('时间均为2026年11月5日北京时间；起点含、终点不含。每个窗口的10个30秒分段均观测到9个不同线程，最小grpThreads为9。原始时间戳、线程名和覆盖核对保存在measurement.jtl及summary.json。')
    note('查询优化前窗口预先固定于09:16批次；最终批次沿用该窗口，并以全表数据SHA256核对同一初态。没有从多个基线中重新挑选更慢样本。')
    page()
    h('瓶颈分析与实际优化')
    h('登录证书验证减少重复子进程')
    p('原登录热路径多次调用OpenSSL获取证书元数据。优化后复用已解析的X.509信息，将每次登录的子进程调用由7次降为2次。每次仍验证证书链、签名、有效期、签发者、用户名与数据库公钥绑定，不缓存认证成功结论。对应gm_crypto.py及model_2_denglu.py。')
    h('国密解密使用进程内OpenSSL')
    p('SM2解密将gmssl的C1C2C3编码转换为OpenSSL EVP所需DER，复用最多16个不可变私钥对象，每请求创建独立上下文并验证C3。保留SM4-GCM、防重放、随机Nonce和request_id，以及审计；缺少本机支持时回退原实现。对应native_sm2.py及payment_crypto.py。')
    h('减少读取事务和鉴权字段开销')
    p('用户、商品、购物车相关单次只读查询使用每服务最多2个连接的有界只读池，避免额外只读COMMIT。订单详情多次查询保留一致性事务；鉴权每次查数据库，仅读取必要状态，避免解密无关手机号。写事务、行锁、库存条件扣减与审计持久化保留。对应read_pool.py、auth.py及三个业务服务。')
    h('HTTPS启用受限持久连接')
    p('非调试服务由Werkzeug开发服务器改为Cheroot，配置16个工作线程、最多64个持久连接和10秒超时，减少逐请求TLS建连开销。客户端KeepAlive与请求间隔保持一致。对应wsgi_runtime.py、run.py及requirements.txt。')
    table(['场景','前连接P95 ms','后连接P95 ms','SQL提交次数 前→后'],[
        ['商品查询','4','0','13506 → 36'],['下单','18','0','37464 → 29854'],['登录','5','0','11728 → 12956']
    ],[3.2,3.5,3.5,6.4])
    note('连接P95取正式窗口；COMMIT为完整运行摘要增量，含初始化。登录优化后完成的请求更多，COMMIT总次数增加；不能据此认定每请求开销增加。SQL摘要及进程采样支持开销分析，未进行函数级因果剖析。')
    p('首版仅业务读路径优化时，商品查询P95由9ms降至8ms，改善11.11%，未达到20%。加入服务器连接复用后降至7ms。未引入Redis，也未新增数据库索引，报告不将这些课程示例写成已实施项目。')
    page()
    h('资源监控与业务正确性')
    table(['场景','阶段','后端CPU\n均值 单核%','私有内存\n峰值MB','DB连接\n采样峰值','锁等待\n采样峰值'],[
        [NAMES[k],STAGES[s],fmt(runs[s,k]['resources']['backend_cpu_percent_one_core']['mean']),fmt(runs[s,k]['resources']['backend_private_mb']['max']),int(runs[s,k]['resources']['db_connections']['max']),int(runs[s,k]['resources']['db_lock_waits']['max'])]
        for k in KEYS for s in ['before','after','retest']
    ],[2.4,2.5,3.2,3.0,2.8,2.7])
    p('资源每2秒采样，表中均为正式窗口。CPU按一个逻辑核心为100%计；本机有16个逻辑处理器。Python进程CPU不包含短命OpenSSL子进程，应结合monitor.csv的整机CPU读取。采样未观测到MySQL锁等待，不能推断任意更高负载也无锁竞争。')
    table(['阶段','全程成功订单','新增订单','库存扣减件数','一致性'],[
        [STAGES[s],runs[s,'order']['db_orders_created'],runs[s,'order']['db_orders_created'],runs[s,'order']['db_stock_consumed'],'一致'] for s in ['before','after','retest']
    ],[3.2,3.4,3.4,3.4,3.2])
    note('订单核对覆盖完整390秒运行，因此大于正式300秒下单样本数。每场景从相同副本初态恢复，未向原数据库创建测试订单。')
    h('回归与安全语义核对')
    p('优化版回归测试46项通过，独立复测前再次46项通过。SM2兼容、并发、密文篡改拒绝，以及HTTP持久连接在401提前返回后下一请求的正确性均有测试记录。集成核对中，有效Token返回200，更新安全版本或禁用用户后立即返回401，TLS与HSTS仍生效。')
    p('源文件清单在测试期间保持一致；复测源码与上次优化版相同，初始数据库全表指纹相同。原JMX未改，临时库与测试进程已清理。数据包没有复制证书、CSV密码或响应Token。')
    h('结果的适用范围')
    p('本结论仅适用于当前小规模数据、9个用户及既定等待时间，服务器与JMeter共用一台电脑。测试未覆盖20个独立用户、极限容量、真实网络或真实支付，未宣称最大QPS或长期无内存泄漏。单轮300秒样本和毫秒级计时存在自然波动；最新下单P95从16ms变为20ms已完整保留。')
    page()
    h('课程要求与交付证据')
    table(['性能要求','证据与结论'],[
        ['三类接口基线','登录、商品列表查询、创建订单均有优化前记录、优化后记录及独立复测。'],
        ['持续测试与四项指标','9个正式窗口各300秒，保存并发数、固定窗口吞吐量、P95与错误率；每30秒验证9线程覆盖。'],
        ['P95下降不少于20%','配对比较登录58.05%、商品查询22.22%、下单81.40%；复测较同一固定基线分别下降59.51%、22.22%、76.74%。'],
        ['错误率不高于1%','优化前、优化后及复测全程HTTP与业务断言错误均为0%。'],
        ['瓶颈分析和真实优化','提供子进程合并、进程内SM2、只读池、精简鉴权和HTTPS持久连接的源码、补丁、配置及监控。'],
        ['可复现交付','保留实际执行JMX、命令、数据指纹、源文件SHA256、原始JTL、图表及SQL摘要。本报告不代替小组周计划、个人贡献和仓库提交记录。'],
    ],[4.2,12.4])
    h('证据目录')
    p('所有目录均位于 D:/学习/综设3/89周-JMeter。')
    table(['目录或文件','内容'],[
        ['完整测试结果-20261105-013809','before与after各三个场景；代码变更、历史基线、优化过程记录、SHA256清单及原报告。'],
        ['优化后复测结果-20261105-103455','query、order、login独立复测；完整复测报告、指标及SHA256清单。'],
        ['三个性能测试JMX','登录性能测试.jmx、商品查询性能测试.jmx、下单性能测试.jmx；原始用户模板保留。'],
        ['本总报告目录','Word与HTML报告、完整指标.csv、P95图、总报告核验.json；汇总引用上述实测证据，不重写原始结果。'],
    ],[6.3,10.3])
    p('查看原始证据时，先打开对应场景settings.json确认命令和实际plan-executed.jmx，再查看measurement.jtl、measurement-html/index.html、monitor.csv及database-before/after.json。复现实验需使用隔离测试库；不要直接在原业务库循环下单。复测脚本为项目performance/rerun_optimized.py，命令为venv/Scripts/python.exe -X utf8 -m performance.rerun_optimized。')
    h('历史数据与来源说明')
    p('凌晨历史基线两轮查询P95为8ms，因此若改用历史值比较，8ms至7ms仅改善12.5%。本报告达标判断固定使用同快照配对基线9ms，历史数据作为旁证单独保留；各批次不混合计算分位数。')
    note('课程依据：安全电子商务系统III第一次课 第30、34、36、52至54页；第4至12周学生小组实施计划中的第9周里程碑。两份材料要求性能基线与优化证据；本次采用300秒正式窗口提供持续性记录。')
    render_docx(blocks)
    render_text(blocks)
    with (OUT/'完整指标.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(metrics[0]));w.writeheader();w.writerows(metrics)
    evidence={'generated_at':datetime.now(TZ).isoformat(),'formal_windows':9,'users_each':9,'formal_seconds_each':300,'formal_business_samples':total,'all_http_samples':rawtotal,'all_requests_successful':True,'paired_source':str(PAIR),'retest_source':str(RETEST),'source_sha256':sources,'summary_crosschecked_against_all_jtl':True,'source_manifests_verified':True,'regression_tests_passed_each':46,'original_database_unchanged':True,'notes':['This report summarizes existing runs; no new load test was executed.','Query baseline was fixed in the prior stage and reused after full seed fingerprint verification.']}
    (OUT/'总报告核验.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'output':str(OUT),'formal_samples':total,'raw_samples':rawtotal,'blocks':len(blocks)},ensure_ascii=False))

def render_docx(blocks):
    doc=Document();sec=doc.sections[0]
    sec.page_width=Cm(21);sec.page_height=Cm(29.7)
    sec.top_margin=sec.bottom_margin=Cm(1.8);sec.left_margin=sec.right_margin=Cm(2.2)
    sec.footer_distance=Cm(.8)
    styles=doc.styles
    for name in ['Normal','Title','Heading 1','Heading 2','Caption']:
        s=styles[name];s.font.name='Microsoft YaHei';s._element.get_or_add_rPr().rFonts.set(qn('w:eastAsia'),'Microsoft YaHei');s.font.color.rgb=RGBColor.from_string('172333')
    styles['Normal'].font.size=Pt(10.5);styles['Normal'].paragraph_format.line_spacing=1.1;styles['Normal'].paragraph_format.space_after=Pt(5)
    styles['Title'].font.size=Pt(23);styles['Title'].font.bold=True;styles['Title'].paragraph_format.space_after=Pt(8)
    styles['Heading 1'].font.size=Pt(14);styles['Heading 1'].font.bold=True;styles['Heading 1'].paragraph_format.space_before=Pt(8);styles['Heading 1'].paragraph_format.space_after=Pt(5)
    for style in styles:
        for border in list(style._element.iter(qn('w:pBdr'))):border.getparent().remove(border)
    footer=sec.footer.paragraphs[0];footer.alignment=WD_ALIGN_PARAGRAPH.RIGHT
    footer.add_run('安全电商系统性能测试  |  ')
    fld=OxmlElement('w:fldSimple');fld.set(qn('w:instr'),'PAGE');footer._p.append(fld)
    for r in footer.runs:r.font.size=Pt(8);r.font.color.rgb=RGBColor.from_string('667085')
    next_page=False
    for b in blocks:
        typ=b[0]
        if typ=='page':next_page=True
        elif typ in ['title','h','p','note']:
            para=doc.add_paragraph(b[1],style={'title':'Title','h':'Heading 1','p':'Normal','note':'Normal'}[typ])
            if next_page:para.paragraph_format.page_break_before=True;next_page=False
            if typ=='note':
                para.paragraph_format.space_after=Pt(7)
                for r in para.runs:r.font.size=Pt(8.5);r.font.color.rgb=RGBColor.from_string('576579')
        elif typ=='image':
            para=doc.add_paragraph();para.add_run().add_picture(str(OUT/b[1]),width=Cm(16.6))
            para.paragraph_format.space_after=Pt(4)
        elif typ=='table':
            table=doc.add_table(rows=1,cols=len(b[1]));table.autofit=False
            widths=b[3] or [16.6/len(b[1])]*len(b[1]);scale=16.6/sum(widths)
            for i,col in enumerate(table.columns):col.width=Cm(widths[i]*scale)
            for rowidx,values in enumerate([b[1]]+b[2]):
                cells=table.rows[0].cells if rowidx==0 else table.add_row().cells
                trpr=cells[0]._tc.getparent().get_or_add_trPr();trpr.append(OxmlElement('w:cantSplit'))
                if rowidx==0:trpr.append(OxmlElement('w:tblHeader'))
                for i,val in enumerate(values):
                    cell=cells[i];cell.width=Cm(widths[i]*scale);cell.text=str(val)
                    tcpr=cell._tc.get_or_add_tcPr()
                    margins=OxmlElement('w:tcMar')
                    for edge in ['top','left','bottom','right']:
                        e=OxmlElement('w:'+edge);e.set(qn('w:w'),'45' if edge in ['top','bottom'] else '75');e.set(qn('w:type'),'dxa');margins.append(e)
                    tcpr.append(margins)
                    shade=OxmlElement('w:shd');shade.set(qn('w:fill'),'E9EEF5' if rowidx==0 else ('F6F8FA' if rowidx%2==0 else 'FFFFFF'));tcpr.append(shade)
                    for para in cell.paragraphs:
                        para.paragraph_format.space_after=Pt(1);para.paragraph_format.space_before=Pt(1);para.paragraph_format.line_spacing=1.05
                        for run in para.runs:run.font.size=Pt(9);run.font.bold=rowidx==0
    doc.core_properties.title=NAME;doc.core_properties.subject='第8周性能基线及第9周优化与复测';doc.core_properties.author='项目测试报告';doc.core_properties.keywords='JMeter P95 性能测试 优化复测'
    doc.save(OUT/(NAME+'.docx'))

def render_text(blocks):
    md=[];parts=[]
    for b in blocks:
        typ=b[0]
        if typ=='page':parts.append('<div class="page-break"></div>');continue
        if typ in ['title','h','p','note']:
            text=html.escape(b[1]);tag={'title':'h1','h':'h2','p':'p','note':'p'}[typ]
            parts.append(f'<{tag} class="{typ}">{text}</{tag}>');md.append(('# ' if typ=='title' else '## ' if typ=='h' else '')+b[1]+'\n')
        elif typ=='image':parts.append(f'<img src="{b[1]}" alt="优化前后和复测的P95占固定基线比例">');md.append(f'![P95优化对比]({b[1]})\n')
        elif typ=='table':
            parts.append('<table><thead><tr>'+''.join('<th>'+html.escape(str(x)).replace('\n','<br>')+'</th>' for x in b[1])+'</tr></thead><tbody>')
            md.append('| '+' | '.join(str(x).replace('\n',' ') for x in b[1])+' |\n|'+ '|'.join(['---']*len(b[1]))+'|')
            for row in b[2]:
                parts.append('<tr>'+''.join('<td>'+html.escape(str(x))+'</td>' for x in row)+'</tr>');md.append('| '+' | '.join(map(str,row))+' |')
            parts.append('</tbody></table>');md.append('')
    parts.append('<nav><a href="../完整测试结果-20261105-013809/index.html">优化前后原始结果</a> · <a href="../优化后复测结果-20261105-103455/index.html">独立复测原始结果</a> · <a href="安全电商系统性能测试总报告.docx">下载Word</a> · <a href="完整指标.csv">完整指标</a></nav>')
    css='body{font:16px/1.8 "Microsoft YaHei",sans-serif;color:#172333;max-width:1120px;margin:40px auto;padding:0 28px}h1{font-size:32px;color:#111}h2{font-size:21px;margin-top:30px}table{border-collapse:collapse;width:100%;font-size:14px;margin:16px 0}td,th{padding:9px 11px;text-align:left;border-bottom:1px solid #dfe5ed}th{background:#e9eef5}tr:nth-child(even){background:#f6f8fa}.note{color:#576579;font-size:14px}img{width:100%;height:auto}nav{padding:25px 0}.page-break{margin-top:40px}@media print{.page-break{break-before:page}body{margin:0}nav{display:none}}'
    (OUT/'index.html').write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>'+NAME+'</title><style>'+css+'</style><main>'+''.join(parts)+'</main></html>',encoding='utf-8')
    (OUT/(NAME+'.md')).write_text('\n'.join(md),encoding='utf-8')

if __name__=='__main__':build()
