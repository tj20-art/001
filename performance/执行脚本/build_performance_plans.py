"""Build project-specific JMeter copies from the user's validated template."""
from copy import deepcopy
import csv
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent
SOURCE = Path('D:/学习/综设3/89周-JMeter/安全电商系统性能测试.jmx')
OUT = ROOT / 'performance/plans'
ACCOUNTS = ROOT / 'performance/data/users-local.csv'


def prop(node, name, value, kind='stringProp'):
    old = node.find(f"*[@name='{name}']")
    if old is None:
        old = ET.SubElement(node, kind, name=name)
    old.tag = kind
    old.text = str(value).lower() if isinstance(value, bool) else str(value)
    return old


def element(kind, gui, name):
    return ET.Element(kind, guiclass=gui, testclass=kind, testname=name, enabled='true')


def add(tree, node, children=None):
    tree.append(node)
    child_tree = ET.SubElement(tree, 'hashTree')
    if children is not None:
        for child in children:
            child_tree.append(deepcopy(child))
    return child_tree


def assertion(path, expected=None, name=None):
    node = element('JSONPathAssertion', 'JSONPathAssertionGui', name or f'检查{path}')
    prop(node, 'JSON_PATH', path)
    prop(node, 'EXPECTED_VALUE', '' if expected is None else expected)
    for key, value in [('JSONVALIDATION', expected is not None), ('EXPECT_NULL', False),
                       ('INVERT', False), ('ISREGEX', False)]:
        prop(node, key, value, 'boolProp')
    return node


def timer(milliseconds):
    node = element('ConstantTimer', 'ConstantTimerGui', '固定请求间隔')
    prop(node, 'ConstantTimer.delay', '${__P(delay_ms,' + str(milliseconds) + ')}')
    return node


def groovy_assert(name, script):
    node = element('JSR223Assertion', 'TestBeanGUI', name)
    for key, value in [('scriptLanguage', 'groovy'), ('cacheKey', 'true'),
                       ('filename', ''), ('parameters', ''), ('script', script)]:
        prop(node, key, value)
    return node


def csv_config():
    node = element('CSVDataSet', 'TestBeanGUI', '账号CSV（每线程固定一行，最多9线程）')
    for key, value in [('filename', '${__P(accounts,' + ACCOUNTS.as_posix() + ')}'),
                       ('fileEncoding', 'UTF-8'), ('variableNames', 'cert_path,password,product_id'),
                       ('delimiter', ','), ('shareMode', 'shareMode.all')]:
        prop(node, key, value)
    for key, value in [('ignoreFirstLine', False), ('quotedData', True),
                       ('recycle', False), ('stopThread', True)]:
        prop(node, key, value, 'boolProp')
    return node


def raw_body(node, body):
    args = node.find("elementProp[@name='HTTPsampler.Arguments']/collectionProp")
    args.clear()
    args.set('name', 'Arguments.arguments')
    arg = ET.SubElement(args, 'elementProp', name='', elementType='HTTPArgument')
    prop(arg, 'HTTPArgument.always_encode', False, 'boolProp')
    prop(arg, 'Argument.value', body)
    prop(arg, 'Argument.metadata', '=')
    prop(node, 'HTTPSampler.postBodyRaw', True, 'boolProp')


def build(scenario):
    original = ET.parse(SOURCE).getroot()
    source_tree = original.find('hashTree/hashTree')
    group_tree = source_tree.find('ThreadGroup')
    source_children = list(source_tree)
    group_tree = source_children[source_children.index(group_tree) + 1]
    children = list(group_tree)
    sources = {}
    for i in range(0, len(children), 2):
        node, subtree = children[i:i + 2]
        if node.tag == 'HTTPSamplerProxy':
            sources[node.find("stringProp[@name='HTTPSampler.path']").text] = (node, subtree)
        elif node.tag == 'ConfigTestElement':
            defaults = node

    root = ET.Element('jmeterTestPlan', version='1.2', properties='5.0', jmeter='5.6.3')
    top = ET.SubElement(root, 'hashTree')
    plan = deepcopy(original.find('hashTree/TestPlan'))
    plan.set('testname', '下单性能测试' if scenario == 'order' else '登录性能测试')
    prop(plan, 'TestPlan.comments', '默认9线程、每线程1次。持续测试用-Jloops=-1 -Jduration=390；先确认PERF_TEST_MODE=1。')
    variables = plan.find("elementProp[@name='TestPlan.user_defined_variables']/collectionProp")
    variables.clear()
    variables.set('name', 'Arguments.arguments')
    v = ET.SubElement(variables, 'elementProp', name='quantity', elementType='Argument')
    prop(v, 'Argument.name', 'quantity')
    prop(v, 'Argument.value', '${__P(quantity,1)}')
    prop(v, 'Argument.metadata', '=')
    plan_tree = add(top, plan)

    # GUI debugging and summary are available; CLI runners disable the full tree.
    listener = deepcopy(source_tree.find('ResultCollector'))
    add(plan_tree, listener)
    aggregate = deepcopy(listener)
    aggregate.set('guiclass', 'StatVisualizer')
    aggregate.set('testname', 'Aggregate Report')
    add(plan_tree, aggregate)

    group = element('ThreadGroup', 'ThreadGroupGui', '下单线程组' if scenario == 'order' else '登录线程组')
    prop(group, 'ThreadGroup.num_threads', '${__P(users,9)}')
    prop(group, 'ThreadGroup.ramp_time', '${__P(ramp,9)}')
    prop(group, 'ThreadGroup.same_user_on_next_iteration', True, 'boolProp')
    prop(group, 'ThreadGroup.on_sample_error', 'stopthread')
    prop(group, 'ThreadGroup.scheduler', True, 'boolProp')
    prop(group, 'ThreadGroup.duration', '${__P(duration,390)}')
    prop(group, 'ThreadGroup.delay', '0')
    outer = ET.SubElement(group, 'elementProp', name='ThreadGroup.main_controller',
                          elementType='LoopController', guiclass='LoopControlPanel',
                          testclass='LoopController', testname='外层只执行一次')
    prop(outer, 'LoopController.loops', '1')
    prop(outer, 'LoopController.continue_forever', False, 'boolProp')
    work = add(plan_tree, group)
    defaults = deepcopy(defaults)
    prop(defaults, 'HTTPSampler.connect_timeout', '10000')
    prop(defaults, 'HTTPSampler.response_timeout', '15000')
    add(work, defaults)
    add(work, csv_config())

    login, login_children = map(deepcopy, sources['/api/v1/auth/login'])
    for file_arg in login.findall(".//elementProp[@elementType='HTTPFileArg']"):
        file_arg.set('name', '${cert_path}')
        prop(file_arg, 'File.path', '${cert_path}')
    for argument in login.findall(".//elementProp[@elementType='HTTPArgument']"):
        if argument.find("stringProp[@name='Argument.name']").text == 'password':
            prop(argument, 'Argument.value', '${password}')
    add(login_children, assertion('$.data.access_token', name='检查登录已获得Token'))
    add(login_children, assertion('$.data.user_info.role', 'user', '检查普通用户角色'))

    if scenario == 'order':
        init = add(work, element('OnceOnlyController', 'OnceOnlyControllerGui', '初始化：登录、公钥、购物车检查'))
        add(init, login, list(login_children))
        key, key_children = map(deepcopy, sources['/api/v1/security/public-key'])
        add(init, key, list(key_children))
        check_cart, _ = map(deepcopy, sources['/api/v1/products'])
        check_cart.set('testname', '准备_检查购物车为空')
        prop(check_cart, 'HTTPSampler.path', '/api/v1/cart/items')
        cart_check_tree = add(init, check_cart)
        headers = deepcopy(sources['/api/v1/orders'][1].find('HeaderManager'))
        collection = headers.find('collectionProp')
        for header in list(collection):
            if header.find("stringProp[@name='Header.name']").text != 'Authorization':
                collection.remove(header)
        add(cart_check_tree, headers)
        add(cart_check_tree, assertion('$.code', '0'))
        add(cart_check_tree, groovy_assert('测试前购物车必须为空', '''import groovy.json.JsonSlurper
def body = new JsonSlurper().parseText(prev.getResponseDataAsString())
if (!(body.data?.items instanceof List) || !body.data.items.isEmpty()) {
    AssertionResult.setFailure(true)
    AssertionResult.setFailureMessage('请先在网页清空此测试账号的购物车；脚本不会自动删除已有商品。')
}'''))

    loop = element('LoopController', 'LoopControlPanel', '业务循环（默认1次，-Jloops=-1持续运行）')
    prop(loop, 'LoopController.loops', '${__P(loops,1)}')
    prop(loop, 'LoopController.continue_forever', False, 'boolProp')
    business = add(work, loop)
    if scenario == 'login':
        login_tree = add(business, login, list(login_children))
        add(login_tree, timer(1000))
    else:
        cart, cart_children = map(deepcopy, sources['/api/v1/cart/items'])
        raw_body(cart, '{"product_id":${product_id},"quantity":${quantity}}')
        cart_tree = add(business, cart, list(cart_children))
        add(cart_tree, timer(500))
        order, order_children = map(deepcopy, sources['/api/v1/orders'])
        order_tree = add(business, order, list(order_children))
        add(order_tree, timer(500))
        add(order_tree, assertion('$.data.order.id', name='检查订单ID存在'))
        add(order_tree, groovy_assert('检查下单状态与商品数量', '''import groovy.json.JsonSlurper
def body = new JsonSlurper().parseText(prev.getResponseDataAsString())
def order = body.data?.order
def items = order?.items
def valid = prev.getResponseCode() == '201' && items instanceof List && items.size() == 1
if (valid) {
    valid = items[0].product_id.toString() == vars.get('product_id') &&
        (items[0].quantity as int) == (vars.get('quantity') as int) &&
        (order.total_amount_cents as long) == (items[0].price_cents as long) * (items[0].quantity as long)
}
if (!valid) {
    AssertionResult.setFailure(true)
    AssertionResult.setFailureMessage('订单应返回201，且只包含本次测试商品、指定数量和正确金额。')
}'''))
    ET.indent(root, space='  ')
    path = OUT / ('下单性能测试.jmx' if scenario == 'order' else '登录性能测试.jmx')
    ET.ElementTree(root).write(path, encoding='UTF-8', xml_declaration=True)
    # Dependency, structure, and secret checks. Password must live only in CSV.
    text = path.read_text(encoding='utf-8')
    assert 'Tj200625' not in text
    for filename in root.findall('.//JSR223PreProcessor/stringProp[@name="filename"]') + root.findall('.//JSR223PostProcessor/stringProp[@name="filename"]'):
        assert Path(filename.text).is_file(), filename.text
    for tree in root.iter('hashTree'):
        nodes = list(tree)
        assert len(nodes) % 2 == 0
        assert all(nodes[i + 1].tag == 'hashTree' for i in range(0, len(nodes), 2))
    print(path)


if __name__ == '__main__':
    with ACCOUNTS.open(encoding='utf-8-sig', newline='') as stream:
        rows = list(csv.reader(stream))
    assert len(rows) == 9 and len({r[0] for r in rows}) == 9
    assert all(len(row) == 3 and Path(row[0]).is_file() for row in rows)
    OUT.mkdir(parents=True, exist_ok=True)
    build('order')
    build('login')
