"""Build Chinese reports strictly from retained tool results and actual commits."""
from collections import Counter
import csv
import hashlib
import html
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET
import zipfile

OUT = Path(__file__).resolve().parent.parent
ROOT = OUT.parents[1]
RAW = OUT / "原始证据"


def read(name):
    return json.loads((RAW/name).read_text(encoding="utf-8"))


def write(name,text):
    if name == "03_扫描与验收复现说明.md":
        text = text.replace("\\\\", "\\")
    (OUT/name).write_text(text.strip()+"\n",encoding="utf-8")


def bandit(phase):
    d=read("bandit-"+phase+".json")
    return {"count":len(d["results"]),"severity":dict(Counter(r["issue_severity"] for r in d["results"])),
            "loc":d["metrics"]["_totals"]["loc"],"rules":dict(Counter(r["test_id"] for r in d["results"]))}


def main():
    before,after=read("http-before.json"),read("http-after.json")
    for result,key in [(before,"vulnerable"),(after,"fixed")]:
        assert all(c.get(key,c.get("passed",True)) for c in result["checks"]),"HTTP evidence contains a failed assertion"
    tests=ET.parse(RAW/"pytest-after.xml").getroot().find("testsuite")
    assert tests is not None and tests.attrib["failures"]=="0" and tests.attrib["errors"]=="0"
    assert "Build complete" in (RAW/"frontend-build-after.log").read_text(encoding="utf-8")
    crypto=read("frontend-crypto-after.log")
    assert crypto["knownCiphertext"]=="681edf34d206965e86b3e94f536e4246"
    live_text=(RAW/"frontend-tunnel-after.log").read_text(encoding="utf-8")
    live=json.loads(live_text[live_text.index("{"):])
    assert live["encryptedResponseDecrypted"] is True
    npm_before,npm_after=read("npm-audit-before.stdout.txt"),read("npm-audit-after.stdout.txt")
    prod=read("npm-audit-production-after.json")
    nb,na=npm_before["metadata"]["vulnerabilities"],npm_after["metadata"]["vulnerabilities"]
    assert "axios" not in npm_after["vulnerabilities"] and "sm-crypto" not in npm_after["vulnerabilities"]
    pip=read("pip-audit-after.json")
    packages=[p for p in pip["dependencies"] if p.get("vulns")]
    advisory_count=len({(p["name"],v["id"]) for p in packages for v in p["vulns"]})
    bb,ba=bandit("before"),bandit("after")
    zb,za=read("zap-before-execution.json"),read("zap-after-execution.json")
    alerts_before,alerts_after=read("zap-before-alerts.json")["alerts"],read("zap-after-alerts.json")["alerts"]
    git=json.loads((OUT/"修复记录/提交记录.json").read_text(encoding="utf-8"))
    commit=git["fix_commit"]
    environment=read("environment.json")
    summary={"group":"第一组","leader":"唐杰","date":"2026-10-14","closed_application_classes":3,
        "bandit_before":bb,"bandit_after":ba,"npm_before":nb,"npm_after":na,"npm_production_after":prod["metadata"]["vulnerabilities"],
        "pip_affected_declared_packages":len(packages),"pip_package_advisory_pairs":advisory_count,
        "pytest_passed":int(tests.attrib["tests"]),"http_cases":len(after["checks"]),"http_all_passed":True,
        "zap_before_messages":zb["message_count"],"zap_after_messages":za["message_count"],
        "zap_before_alerts":len(alerts_before),"zap_after_alerts":len(alerts_after),"fix_commit":commit,
        "limitations":["remaining dependency and configuration risks are open","fixture JWTs do not prove complete certificate/MFA login",
            "V3 uses explicit fault injection","no browser-based stored XSS testing","no push to group remote and no invented teammate contributions"]}
    (OUT/"结果摘要.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")

    write("00_先读这个.md",f"""
# 第一组第七周安全验收材料

组长：唐杰。整理日期：2026年10月14日。项目：安全电子商务系统III。

本次完成了实际 SAST、ZAP DAST、前后端依赖扫描，复现并修复三类应用漏洞，保存修复前后 HTTP 证据、真实本地 Git 提交和回归结果。另修复模拟银行调试默认值、默认监听范围，补充 API 安全响应头，并升级 Axios 与 sm-crypto。代码修改已应用到原项目。

全部 {tests.attrib['tests']} 项后端测试通过；{len(after['checks'])} 项 HTTP 检查达到预期；前端 SM4 标准向量、前后端安全隧道测试和生产构建通过。

依赖风险尚未全部清零：前端完整依赖扫描仍有 {na['total']} 个受影响依赖项，后端声明依赖有 {len(packages)} 个受影响包。开发配置还有 JWT 密钥硬编码回退。详细处理计划在《04_阻断级与剩余风险处理计划》。本材料证明本次测试范围和三类漏洞闭环，不能作为可安全对外发布的证明。

## 建议阅读顺序

1. [安全基线与复扫报告](01_安全基线与复扫报告.md)：看范围、工具版本、扫描前后数据和限制。
2. [漏洞清单与修复闭环](02_漏洞清单与修复闭环.md)：看三类漏洞如何复现、修复及验证。
3. [扫描与验收复现说明](03_扫描与验收复现说明.md)：按命令重新执行。
4. [阻断级与剩余风险处理计划](04_阻断级与剩余风险处理计划.md)：看未完成风险及负责人。
5. [第一组第7周推进计划](05_第一组第7周推进计划.md)：组长检查并补齐成员姓名。
6. [验收演示与测试数据说明](06_验收演示与测试数据说明.md)：用于现场演示。

## 新增目录分别表示什么

| 目录或文件 | 意义 | 是否进入提交包 |
|---|---|---|
| 00—07 开头的中文文档 | 最终报告、计划、文件说明 | 是 |
| 原始证据 | 真实扫描 JSON、HTTP 请求响应、测试与构建日志；Authorization 已脱敏 | 是 |
| 修复记录/修复前源码、修复后源码 | 本次修改涉及文件的前后快照；不是完整系统发布包 | 是 |
| 修复记录/修复补丁.patch | 本次代码和依赖变更的统一补丁 | 是 |
| 修复记录/week7-fixes.bundle | 保存真实前后两个本地 Git 提交的离线文件 | 是 |
| 修复记录/证据仓库 | 本地对照仓库，与原前端仓库分开 | 以 bundle 形式提交 |
| 脚本 | 重跑扫描、隔离攻击测试、报告生成的脚本 | 是 |
| .tools | 便携 ZAP、Python 扫描环境和临时测试状态；含本地测试认证材料 | 否 |
| 结果摘要.json、文件校验清单.json | 数据摘要与 SHA-256 文件清单 | 是 |

本地修复提交：`{commit}`。这是本次新建证据仓库的真实提交，作者为 Codex security verification。没有冒充组员提交，也没有向小组远程仓库推送。

小组仍需把材料与修复合并进正式小组仓库，补充其他成员姓名、上周计划兑现情况及各自真实提交。老师是否通过验收需要现场确认。
""")

    write("01_安全基线与复扫报告.md",f"""
# 第七周安全基线与复扫报告

第一组，组长唐杰，2026年10月14日。

本次目标对应实施计划第7周节点及第一次课课件第49—51页：完成 SAST、DAST、依赖扫描，并保存三类不同漏洞的复现、评级、修复提交和回归证据。SQL注入、XSS、IDOR是课件举例，并非必须人为制造这三种漏洞。

## 环境和范围

实际使用 Windows、Python {environment['python'].split()[0]}、Node {environment['node']}、MySQL。后端实际安装版本与 `requirements.txt` 声明一致，详见 `原始证据/environment.json`。测试服务仅绑定本机 HTTPS 2445/2446，使用脚本新建的 `week7_test_20261014_*` 独立数据库，不修改业务库 adb 的数据。

SAST 工具为 Bandit 1.9.4，扫描 `api_service4/app`、`api_service4/run.py` 和 `mock_bank`。配置文件另做脱敏 AST 检查；不把 Bandit 当作 JavaScript 扫描器。前端检查依赖与模板危险用法，未发现 `v-html`/`innerHTML` 直接写入位置，但没有据此宣称全部 XSS 风险消失。

DAST 使用官方 ZAP {zb['version']['version']}，其 bundled active/passive rules 实际加载。ZAP 插件自动更新连接曾失败，日志已保留；本次使用随官方发行包附带的规则，具体版本在 execution JSON。主动扫描仅针对公开商品查询的 SQL Injection 和 Cross Site Scripting (Reflected) 规则，LOW 强度、单线程、1400ms 请求间隔、最长3分钟。主动扫描没有对外站点、支付或删除接口发起攻击。

经 ZAP 代理发送带测试身份的 RBAC/审计导出请求与有效 SM2+SM4-GCM 请求。认证身份由隔离夹具签发 JWT；未通过真实证书登录/TOTP流程获取会话，不能将该部分作为完整登录流程验收证据。测试进程针对本机临时自签名证书使用 `verify=False`，不修改业务代码的 TLS 校验。

V3 使用明确标注的故障注入，使真实商品查询处理函数抛出合成异常，并观察真实 HTTPS 响应；没有人为断开生产数据库。CSV 测试以数据库预置的无害 `=1+1` 值证明旧导出的处理缺陷，未打开 Excel 执行危险公式。

## 扫描前后数据

| 指标 | 修复前 | 修复后 | 解释 |
|---|---:|---:|---|
| Bandit 总告警 | {bb['count']} | {ba['count']} | 自动告警数，不能等同实际漏洞数 |
| Bandit 高危 | {bb['severity'].get('HIGH',0)} | {ba['severity'].get('HIGH',0)} | 模拟银行 debug=True 告警已消失 |
| Bandit 中危 | {bb['severity'].get('MEDIUM',0)} | {ba['severity'].get('MEDIUM',0)} | 默认全网监听2处已改为本机 |
| Bandit 低危 | {bb['severity'].get('LOW',0)} | {ba['severity'].get('LOW',0)} | 逐类复核见下文 |
| ZAP 纳入报告的消息 | {zb['message_count']} | {za['message_count']} | 主动扫描各发送31个请求，均 FINISHED/100% |
| ZAP 告警实例 | {len(alerts_before)} | {len(alerts_after)} | 同一规则在多个URL的告警实例，不是独立漏洞数 |
| npm 受影响依赖项（含开发） | {nb['total']} | {na['total']} | Axios、sm-crypto等版本变更降低数量 |
| npm critical / high | {nb['critical']} / {nb['high']} | {na['critical']} / {na['high']} | 剩余项目未标为修复 |
| pip-audit 受影响声明包 | {len(packages)} | {len(packages)} | 后端依赖尚未迁移 |

pip-audit 对12个固定版本声明依赖使用 `--no-deps --disable-pip`。有 {advisory_count} 条去重的“包名＋advisory ID”记录；不代表 {advisory_count} 个互不重叠的独立 CVE，亦未扫描未列出的全部传递依赖。

## Bandit 复核

| 规则 | 修复后数量 | 复核与处置 |
|---|---:|---|
| B608 动态 SQL | {ba['rules'].get('B608',0)} | 复核发现动态内容来自内部字段白名单、固定数据库时间表达式或占位符数量，外部值独立绑定；未证实SQL注入。保留告警，不使用忽略配置删除原始结果 |
| B105 密码字面量 | {ba['rules'].get('B105',0)} | 命中字段名、DDL或验证规则，未发现这6处实际包含密码值；不包含单独配置检查出的JWT回退风险 |
| B404/B603 子进程 | {ba['rules'].get('B404',0)+ba['rules'].get('B603',0)} | OpenSSL 固定参数列表、未使用 shell=True；路径依赖PATH，需要部署时固定可信可执行文件 |
| B110 捕获异常后继续 | {ba['rules'].get('B110',0)} | 多格式证书解析/兼容回退；属于需持续测试的代码质量风险，未证明可利用 |
| B311 非密码随机数 | {ba['rules'].get('B311',0)} | 用于订单编号；不是密钥、Nonce或认证Token。订单访问有归属检查；不得改作安全凭据 |

## DAST 复核

修复前的缺少 `X-Content-Type-Options` 和 HSTS 告警在修复后消失。补充 CSP、X-Frame-Options、Referrer-Policy 与敏感API `no-store`。

修复后仍有开发服务器版本信息、缓存策略提示和一次“Application Error Disclosure”。其中应用错误告警的 evidence 仅为 HTTP 500 状态行；实际响应只含通用错误，合成内部标记已经消失，判定本次实例为状态行导致的误报。缓存提示为 informational，敏感 API 采用 no-store 是预期设计。版本信息是本机 Werkzeug 测试服务器的部署风险，仍需在生产网关处理。

SQLi/XSS主动扫描没有新增告警；这仅说明当前规则、请求与范围未检出，不能证明全系统无漏洞。商品ID注入返回400，商品名注入未返回他人数据；普通用户管理接口返回403，外来订单返回404。跨域JSON写请求被安全信封/CORS拒绝；未完成multipart端点的全面CSRF测试，也未做浏览器存储型/DOM XSS验证。

## 回归结果与结论

三类应用漏洞均在同样的攻击/故障条件下完成前后对照；{len(after['checks'])} 项 HTTP 检查达到预期；pytest {tests.attrib['tests']}项全部通过，0失败、0错误；前端密码标准向量、真实安全隧道和生产构建通过。构建日志保留其原有性能提示。

本次代码修复和第7周本地验收证据已经形成，剩余依赖、JWT配置及覆盖范围问题有处理计划，不能据此认定可直接对外上线。正式小组仓库提交和其他成员真实贡献需小组补齐。
""")

    write("02_漏洞清单与修复闭环.md",f"""
# 漏洞清单与修复闭环

第一组，组长唐杰，2026年10月14日。以下风险评级为本次教学项目的定性评级，不是自行编造的CVSS分值。

## 三类应用漏洞

| 编号 | 类型与评级 | 修复前 | 修复后 | 状态 |
|---|---|---|---|---|
| V1 | 登录限流身份信任缺陷；CWE-307/CWE-807；高危 | 同一真实IP改变X-Forwarded-For，12次请求均未触发429 | 第11、12次请求均返回429 | 已复现、修复、回归 |
| V2 | CSV公式注入；CWE-1236；中危 | 审计导出单元格为 `=1+1` | 单元格为 `'=1+1` | 已复现、修复、回归 |
| V3 | 内部错误信息泄露；CWE-209；中危 | 商品查询500响应包含合成数据库/表/驱动信息 | 状态仍500，但响应不含内部标记，details仅为internal_error | 已故障注入复现、修复、回归 |

三者分别属于身份与访问频率控制、导出内容处理、错误信息管理。不是将同一种漏洞的三个实例凑成三类。

### V1 登录限流绕过

发现来源：代码审阅，随后在真实HTTPS端点验证。原限流标识直接读取X-Forwarded-For，客户端可以自由改值。对同一端口连续发送12次 `POST /api/v1/auth/login`，每次换一个 `198.51.100.*` 转发头；请求故意缺少登录表单，证明请求是否穿过限流层，不进行密码猜测或锁定真实用户。

修复：IP标识只使用服务器 remote_addr；登录和注册始终共用真实网络来源的限流预算，不能利用Bearer头切换用户身份重置额度；过期Token不再用于限流身份；审计IP也不直接信任X-Forwarded-For。影响：反向代理后多个匿名用户可能共享代理IP额度，生产部署须通过严格可信代理配置解决，不能重新启用任意转发头信任。

证据：`原始证据/http-before.json`、`http-after.json` 的V1及其12条原始请求；对应pytest测试包含换头、切换有效Bearer、过期Token和不同真实IP的正反用例。

### V2 审计CSV公式注入

发现来源：导出代码审阅及带审计员测试会话的真实HTTP导出。以隔离数据库预置无害 `=1+1` 审计字段模拟历史恶意/外部记录。未把该预置步骤称为互联网直接写入任意审计字段的证明。旧代码只用csv.DictWriter转义CSV分隔符，不能阻止表格软件把公式当作表达式。

修复：对所有导出列逐值处理，字符串以 `= + - @` 开头（含前导空白），或以制表/回车/换行开头时添加文本前缀；正常文本、数字和空值保持原值。导出认证与只读权限不变。

证据：原始HTTP前后记录中的V2及完整CSV正文。测试使用无害 `=1+1`，没有外链、命令或DDE载荷；验证的是CSV内容处理，未实际运行Excel中的危险公式。

### V3 内部错误泄露

发现来源：商品查询异常分支审阅。对真实处理函数 `list_products` 注入合成RuntimeError，文本为 `INTERNAL_ONLY db=week7_fixture table=products driver=pymysql`。服务器实际处理GET请求，修复前将str(exc)返回给客户端。这个测试覆盖异常响应处理，不证明攻击者已获得数据库控制权。

修复：商品查询内部异常只记录到服务端；统一error助手对5xx返回通用提示和internal_error，不把调用点传入的异常文本返回给客户端；正常4xx校验理由保留。服务端日志仍含合成异常，是排障证据，不属于对外响应。

证据：前后HTTP记录V3中的status和body。后端回归同时验证5xx脱敏与4xx有效错误理由。ZAP复扫的90022实例仅命中500状态行，对照body判为本次误报。

## 其他实际改进

| 项目 | 已做改动 | 验证 |
|---|---|---|
| 模拟银行调试模式 | debug=True改为False | Bandit B201高危告警消失；未进行完整银行支付端到端演练 |
| 服务默认监听 | 后端和模拟银行默认127.0.0.1 | 两处B104告警消失；局域网演示需明确设置API_BIND_HOST/MOCK_BANK_HOST |
| API响应头 | nosniff、CSP、拒绝嵌入、HSTS、no-store等 | ZAP缺少nosniff/HSTS实例消失 |
| Axios | 升级至1.20.0并更新锁文件 | 当前npm报告已不含axios条目，生产构建与隧道通过 |
| sm-crypto | 升级至0.5.7并更新锁文件 | 当前npm报告已不含sm-crypto条目，SM4标准向量及SM2封装隧道通过 |
| 前端验证脚本 | Babel插件通过require.resolve定位 | 从正确前端目录和项目根目录均可找到插件 |

以上依赖修复依据公开advisory和实际版本复扫；没有把库CVE写成已经对本系统完成利用的证据。

## 修复代码与Git记录

保存了修改前原样文件和修改后文件。修复提交：`{commit}`；基线提交：`{git['baseline_commit']}`。见 `修复记录/提交记录.json`、`修复补丁.patch`、`week7-fixes.bundle`。

提交来自本次独立本地证据仓库，其基线为当前工作区快照，不是小组历史Git版本。它不会混入原前端仓库中此前已有的大量未提交改动。正式小组仓库的合并/推送及个人贡献由小组据实完成。

分类参考：[CWE-307](https://cwe.mitre.org/data/definitions/307.html)、[CWE-1236](https://cwe.mitre.org/data/definitions/1236.html)、[CWE-209](https://cwe.mitre.org/data/definitions/209.html)、[OWASP CSV Injection](https://community.owasp.org/attacks/CSV_Injection)。
""")

    write("03_扫描与验收复现说明.md",r"""
# 扫描与验收复现说明

以下命令适用于当前Windows项目位置。MySQL需运行，现有开发配置的连接账号需有创建隔离测试库的权限。脚本不修改现有业务库的用户、商品或订单数据；仅创建本次测试库。首次在另一台机器运行需重新安装工具和项目依赖。

## 当前机器直接重跑

打开PowerShell并切换项目根目录：

```powershell
Set-Location 'C:\Users\r7000\PycharmProjects\PythonProject1'
```

执行修复前和修复后的对照。before会通过Python导入钩子加载保存的修复前模块，不会覆盖当前项目文件；两次各自使用新建测试库。运行后自动停止测试端口。

```powershell
.\venv\Scripts\python.exe '.\其它\第7周安全验收\脚本\security_lab.py' before --port 2445
.\venv\Scripts\python.exe '.\其它\第7周安全验收\脚本\security_lab.py' after --port 2446
.\venv\Scripts\python.exe '.\其它\第7周安全验收\脚本\run_regression.py'
```

`before`应显示V1/V2/V3的vulnerable=true；`after`应显示fixed=true，其余检查passed=true。V3明确为故障注入。测试身份由夹具签发JWT，不能拿这次测试冒充证书/MFA登录验收。

SAST和依赖复扫：

```powershell
& '.\其它\第7周安全验收\.tools\scan-env\Scripts\python.exe' '.\其它\第7周安全验收\脚本\run_scans.py' after
```

退出码1可能表示工具发现告警，不等同工具未运行。检查execution JSON、原始结果的有效结构和stderr。npm必须指定官方registry；国内镜像曾不支持audit端点，失败记录已留存。pip-audit只扫描固定版本声明，不包含全部传递依赖。

前端国密和端到端测试：先在一个终端运行 after --hold，再在第二个终端进入前端目录：

```powershell
.\venv\Scripts\python.exe '.\其它\第7周安全验收\脚本\security_lab.py' after --port 2446 --hold
```

```powershell
Set-Location 'C:\Users\r7000\PycharmProjects\PythonProject1\api-service4-frontend'
$env:TUNNEL_TEST_BASE_URL='https://127.0.0.1:2446'
npm run test:crypto
npm run test:tunnel-live
npm run build
```

完成后Ctrl+C停止本次测试服务。测试脚本仅对临时自签名证书关闭TLS校验，不要移植到业务客户端。

## 重跑ZAP

官方便携ZAP已放入.tools，Java需可用。启动ZAP仅监听本机8099：

```powershell
java -Xmx768m -jar '.\其它\第7周安全验收\.tools\zap\ZAP_2.17.0\zap-2.17.0.jar' -daemon -host 127.0.0.1 -port 8099 -dir 'C:\Users\r7000\PycharmProjects\PythonProject1\其它\第7周安全验收\.tools\zap-home' -config api.key=week7-local-scan -config autoupdate.checkOnStart=false -config autoupdate.installAddonUpdates=false
```

另开终端，让完整测试HTTP经过ZAP后保留服务；再开终端执行ZAP主动规则：

```powershell
.\venv\Scripts\python.exe '.\其它\第7周安全验收\脚本\security_lab.py' after --port 2446 --proxy http://127.0.0.1:8099 --hold
& '.\其它\第7周安全验收\.tools\scan-env\Scripts\python.exe' '.\其它\第7周安全验收\脚本\zap_scan.py' after --port 2446
```

修复前复扫把after改为before，端口改为2445。脚本只允许2445/2446，只启用SQLi和反射XSS规则。扫描结束导出alerts、messages、execution三个JSON，消息中的Authorization已脱敏。ZAP插件更新失败不等于未加载规则；核实execution中installedAddons及扫描状态。复扫会覆盖同名结果，保留原交付包可用于对账。

重新安装扫描工具时使用隔离venv：

```powershell
.\venv\Scripts\python.exe -m venv '.\其它\第7周安全验收\.tools\scan-env'
& '.\其它\第7周安全验收\.tools\scan-env\Scripts\python.exe' -m pip install bandit==1.9.4 pip-audit==2.10.1 requests
```

官方ZAP下载与说明：https://github.com/zaproxy/zaproxy/releases/tag/v2.17.0 和 https://www.zaproxy.org/docs/desktop/cmdline/ 。pip-audit说明：https://github.com/pypa/pip-audit 。

## 核验提交

```powershell
git -C '.\其它\第7周安全验收\修复记录\证据仓库' log --oneline
git -C '.\其它\第7周安全验收\修复记录\证据仓库' show --stat HEAD
git -C '.\其它\第7周安全验收\修复记录\证据仓库' bundle verify '..\week7-fixes.bundle'
```

上面的-C指定了已验证的证据仓库。不要把补丁重复应用到已修复的工作区。正式小组仓库需自行合并与推送。
""")

    prod_counts=prod["metadata"]["vulnerabilities"]
    package_rows="\n".join("| "+p['name']+" | "+p['version']+" | "+str(len({v['id'] for v in p['vulns']}))+" | 唐杰，后端依赖迁移 | 未修复 |" for p in packages)
    write("04_阻断级与剩余风险处理计划.md",f"""
# 阻断级与剩余风险处理计划

第一组，组长唐杰，2026年10月14日。该表为拟定分工与处理计划，不代表组员已完成工作。

当前前端完整树仍有 {na['critical']} 个critical、{na['high']} 个high依赖项。仅生产依赖扫描为：critical {prod_counts['critical']}、high {prod_counts['high']}、moderate {prod_counts['moderate']}、low {prod_counts['low']}，总计{prod_counts['total']}。风险评级来自npm，不可把开发工具链告警直接解释为浏览器已经被攻击；仍需关注开发服务器和构建供应链。

## 阻断项和责任

| 编号 | 问题 | 当前措施 | 责任人/岗位 | 完成条件与计划 |
|---|---|---|---|---|
| R1 | 后端旧Flask/Jinja2/Werkzeug/PyJWT/cryptography已知漏洞 | 保留本机隔离验证；尚未升级，不能标记关闭 | 唐杰负责后端迁移，测试岗位复核 | 第8周优先在新venv升级兼容版本并跑全部认证、证书、隧道、订单、支付回归；对外发布前复扫，处理所有适用高危问题 |
| R2 | 前端开发工具链3个critical和37个high项 | 已先升级Axios/sm-crypto；未执行破坏性npm audit fix --force | 唐杰统筹，前端岗位执行（姓名待认领） | 第8周先做兼容更新，再评估Vue CLI/旧工具链迁移；构建、界面、隧道均通过后更新锁文件并复扫 |
| R3 | JWT_SECRET存在源码硬编码回退 | 配置AST发现，实际值未写入报告 | 唐杰 | 第7周检查前明确整改安排；对外发布前取消弱默认值、通过环境/密钥管理提供强密钥，轮换并验证旧Token失效 |
| R4 | 开发WSGI Server版本暴露 | 默认仅本机监听，模拟银行debug已关闭 | 唐杰，部署岗位认领 | 对外发布前使用适当WSGI及TLS网关、限制后端网络访问并处理Server版本头 |
| R5 | multipart端点CSRF、浏览器stored/DOM XSS覆盖不足 | JSON跨域/信封门禁已测试；ZAP完成反射XSS范围 | 唐杰统筹，测试岗位认领 | 第8周补真实浏览器多角色和上传攻击测试；保存原始步骤，不能将当前“未发现”写成全面安全 |
| R6 | JavaScript缺少完整SAST、依赖传递树覆盖不完整 | Python Bandit与npm锁文件扫描已执行 | 前端/测试岗位，唐杰统筹 | 增加支持JS的SAST并覆盖后端传递依赖，复核规则与误报 |

其他成员尚未提供姓名。以上执行岗位由唐杰按实际人数分配，可兼任；总体责任人明确为唐杰。老师现场检查时需补充具体成员及真实提交。

## 后端依赖明细

| 包 | 声明版本 | 去重advisory ID数 | 责任 | 状态 |
|---|---|---:|---|---|
{package_rows}

完整版本建议、别名、漏洞说明见 `原始证据/pip-audit-after.json`。扫描中部分条目没有修复版本，需判断实际代码路径与上游状态；不要为消除报告盲目填入并不存在的版本，也不要只升级manifest不升级实际运行环境。

## 前端剩余清单

每个受影响包的严重性、是否直接依赖、修复建议与来源链接均列于 `依赖风险清单.csv` 和原始npm JSON。severity为critical/high且无法证明不适用的项，在对外发布前完成升级或明确风险接受记录。风险接受不能替代老师要求的三类真实修复。

退出码1在本次Bandit/pip-audit/npm扫描中表示发现告警，报告未被伪装成0问题。当前三类应用漏洞与核心前端依赖已修复，但上述开放项使生产发布条件尚未满足。
""")

    write("05_第一组第7周推进计划.md",f"""
# 第一组第7周推进计划

小组：第一组。周次：第7周。组长：唐杰。填表日期：2026年10月14日。

## 1 上周计划兑现情况

仓库已存在第2/4周安全实现说明和2026年9月17日安全隧道历史测试记录。本次确认相关代码存在，且重新执行后端、前端国密和安全隧道测试通过。上周实际承诺清单、成员分工及老师是否验收未提供，唐杰需逐条补充，不能按现有文件推定已经兑现。

## 2 本周目标

对应第7周SAST/DAST/依赖扫描节点。形成基线、漏洞清单、三类不同漏洞修复与回归闭环，保留工具原始报告、运行环境及Git记录。当前本地已完成这些技术交付；剩余依赖、JWT配置等风险按照04号计划管理。

## 3 分工

| 姓名/岗位 | 负责内容 | 交付物及当前状态 |
|---|---|---|
| 唐杰，组长兼后端负责人 | 统筹、确认需求、后端修复审阅、配置和后端依赖后续迁移、组仓合并 | 审核修复补丁与风险处理计划，合并本地材料；正式提交需唐杰完成 |
| 前端岗位，姓名待唐杰指定 | 核心库升级确认、构建与真实隧道复测、剩余工具链风险整改 | package.json/lock及frontend-*.log已生成；由实际成员认领和验证 |
| 测试岗位，姓名待唐杰指定 | SAST/DAST/依赖复扫、三类漏洞前后对照、误报复核、补浏览器测试 | 原始证据/下的JSON/XML及test_week7_security.py已生成；后续覆盖见风险计划 |
| 文档与验收岗位，姓名待唐杰指定 | 报告核对、数据脱敏、现场演示、成员贡献核对 | 00—07中文文档、证据索引和提交包已生成；成员信息与上周兑现待补 |

此处是职责安排，不假定小组人数；一人可以兼任多个岗位。不得把自动生成的Codex本地提交当作所有组员各自的贡献。

## 4 本周预期交付物

统一目录：`其它/第7周安全验收/`。

- `01_安全基线与复扫报告.md`、`02_漏洞清单与修复闭环.md`。
- `原始证据/bandit-before.json`、`bandit-after.json`、`zap-*-*.json`、`pip-audit-*.json`、`npm-audit-*.stdout.txt`。
- `原始证据/http-before.json`、`http-after.json`、`pytest-after.xml`及前端测试/构建日志。
- `修复记录/提交记录.json`、`修复补丁.patch`、`week7-fixes.bundle`。
- `03_扫描与验收复现说明.md`、`04_阻断级与剩余风险处理计划.md`。

本地修复提交：`{commit}`。上述文件及实际源代码需进入小组正式仓库。

## 5 卡点与需要的帮助

旧后端依赖、旧Vue工具链与JWT硬编码回退仍有风险，已有处理计划。需要明确老师对Bandit作为Python SAST工具、故障注入复现和本地独立Git证据的验收口径；本次未获得教师反馈，不能写成老师已认可。其他成员姓名和正式仓库地址尚未提供，无法代替每名成员完成个人提交。

按实施计划，课堂前将本计划提交组仓；每周四第4节进行5分钟检查，逐项核对每人提交、上周交付物入仓及卡点。代码和报告能本地复现并不自动替代这些课堂管理要求。
""")

    write("06_验收演示与测试数据说明.md",f"""
# 验收演示与测试数据说明

## 5分钟演示安排

1. 展示安全基线与前后扫描统计，说明仍存在依赖风险。
2. 打开http-before/http-after对照V1：12次换转发头请求，修复后第11/12次429。
3. 对照V2导出字段：`=1+1`变为`'=1+1`；无害公式、未执行命令。
4. 对照V3错误body：故障注入标记修复后消失；说明未断开数据库。
5. 展示Git前后两次提交、{tests.attrib['tests']}项pytest通过、前端密码/隧道/构建日志。根据老师要求按03号文档现场重跑。

## 测试数据

脚本在新建数据库注册四个夹具角色：wk7_user、wk7_merchant、wk7_admin、wk7_auditor。密码每次随机生成，不写入提交材料；不提供这些账号作为已完成证书/TOTP登录的演示账号。HTTP测试使用仅针对夹具库的测试JWT，原始消息中的Bearer已经脱敏。

商品为“安全测试商品”，价格10元、库存10；另建立属于其他身份的订单用于IDOR测试；在审计表预置`=1+1`进行CSV处理验证。测试库、上传目录、根证书和隧道密钥均隔离。数据库库名记录在HTTP证据与regression-environment中。

ZAP目标只为127.0.0.1:2445/2446。主动扫描限定公开商品查询参数，并且不会启动银行支付、执行订单删除或访问外部站点。已停止本次临时服务与ZAP进程；重跑时按03号说明启动。

## 当前范围内的正向与拒绝测试

- 正常商品查询200，夹具商品存在。
- 普通用户访问用户管理403，访问其他身份订单404。
- 商品ID注入400，商品名注入无匹配结果。
- 外站Origin发送无安全信封JSON写请求被400拒绝，未获得允许该Origin的CORS头。
- 有效安全信封未认证请求401、业务校验错误400，且响应实际加密并可解密。
- 既有前端到后端脚本验证加密错误响应、重放409、密文/AAD篡改400、过期408及每次随机值变化。

当前没有证明所有SQLi/XSS/CSRF场景均安全，也没有完整银行端到端、真实证书/MFA登录或第9周性能验收结论。相关事项按范围及剩余计划说明，不制造通过记录。
""")

    # Machine-readable risk inventory: leave raw advisory descriptions in originals.
    with (OUT/"依赖风险清单.csv").open("w",encoding="utf-8-sig",newline="") as f:
        fields=["ecosystem","package","version_or_range","severity","advisory_id","source_url","status","owner"]
        writer=csv.DictWriter(f,fieldnames=fields)
        writer.writeheader()
        for name,item in npm_after['vulnerabilities'].items():
            direct=[x for x in item['via'] if isinstance(x,dict)]
            for v in direct or [{}]:
                writer.writerow(dict(ecosystem="npm",package=name,version_or_range=item.get('range'),severity=item['severity'],
                    advisory_id=v.get('source',"传递影响"),source_url=v.get('url','见npm原始报告'),status="未修复/需适用性复核",owner="唐杰统筹，前端岗位认领"))
        for p in packages:
            seen=set()
            for v in p['vulns']:
                if v['id'] in seen:continue
                seen.add(v['id'])
                writer.writerow(dict(ecosystem="PyPI",package=p['name'],version_or_range=p['version'],severity="工具未提供等级，按风险复核",
                    advisory_id=v['id'],source_url="见pip-audit原始报告aliases/description",status="未修复",owner="唐杰"))

    index=[]
    for p in sorted(RAW.iterdir()):
        name=p.name
        if name.startswith('bandit'):meaning='Python静态扫描原始结果或执行信息'
        elif name.startswith('pip-audit'):meaning='后端固定版本声明依赖扫描'
        elif name.startswith('npm-audit'):meaning='前端依赖树扫描，production为仅生产范围'
        elif name.startswith('http-'):meaning='真实HTTP请求响应及断言；Bearer已脱敏'
        elif name.startswith('zap-'):meaning='ZAP报告/请求消息/规则版本/日志'
        elif name.startswith('frontend-'):meaning='前端国密、隧道或生产构建结果'
        elif name.startswith('pytest'):meaning='全部后端回归测试结果'
        else:meaning='环境、配置检查、工具运行或基线复现辅助记录'
        index.append(f'| [{name}](原始证据/{name}) | {meaning} | {p.stat().st_size} |')
    write("07_文件说明与证据索引.md","# 文件说明与证据索引\n\n详细目录用途见00号说明。.tools不进入提交包；原始证据里的Token已脱敏，但HTTP业务响应和合成错误标记原样保留。lab-before.log是首次夹具记录，正式三类证据以http-before.json（已验证快照可复现）及http-before-zap.json（经代理）为准。\n\n| 文件 | 意义 | 字节数 |\n|---|---|---:|\n"+"\n".join(index))

    links=[p for p in sorted(OUT.glob("*.md"))]
    html_text='<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>第一组第七周安全验收</title><style>body{font:17px/1.7 system-ui,"Microsoft YaHei",sans-serif;max-width:960px;margin:48px auto;padding:0 24px;color:#192231;background:#fafafa}h1{font-size:30px}a{color:#1856a8}table{border-collapse:collapse;width:100%;background:white}td,th{padding:12px;border:1px solid #ddd;text-align:left}p{max-width:800px}.note{padding:16px;background:#fff4dc}</style><h1>第一组第七周安全验收</h1><p>组长唐杰 · 2026年10月14日</p><p>完成真实扫描和三类漏洞修复闭环。31项后端测试、前端国密与安全隧道、生产构建通过。</p><p class="note">依赖及配置风险尚未清零；正式组仓提交、成员姓名和真实贡献仍需补充。请先阅读基线报告及剩余处理计划。</p><table><tr><th>报告</th><th>用途</th></tr>'
    for p in links:
        html_text+=f'<tr><td><a href="{html.escape(p.name)}">{html.escape(p.stem)}</a></td><td>UTF-8中文Markdown，使用支持Markdown的编辑器查看</td></tr>'
    html_text+='</table><p><a href="依赖风险清单.csv">依赖风险清单</a> · <a href="结果摘要.json">结果摘要</a> · <a href="修复记录/修复补丁.patch">修复补丁</a></p></html>'
    (OUT/'阅读入口.html').write_text(html_text,encoding='utf-8')
    # Package only reviewable deliverables, not tools, test keys or .git internals.
    files=[]
    for p in sorted(OUT.rglob('*')):
        if not p.is_file():continue
        rel=p.relative_to(OUT)
        if '.tools' in rel.parts or '证据仓库' in rel.parts or '__pycache__' in rel.parts:continue
        if p.suffix=='.zip' or p.name=='文件校验清单.json':continue
        files.append(p)
    hashes=[{'path':str(p.relative_to(OUT)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size} for p in files]
    (OUT/'文件校验清单.json').write_text(json.dumps(hashes,ensure_ascii=False,indent=2),encoding='utf-8')
    package=ROOT/'其它/第一组_第7周安全验收提交包.zip'
    with zipfile.ZipFile(package,'w',zipfile.ZIP_DEFLATED) as z:
        for p in files+[OUT/'文件校验清单.json']:
            z.write(p,Path('第7周安全验收')/p.relative_to(OUT))
    print(json.dumps({'reports':len(links),'package':str(package),'files':len(files)+1,'summary':summary},ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
