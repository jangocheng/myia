
from myia.api import parse
from myia.graph_utils import dfs
from myia.anf_ir import Graph, Constant
from myia.anf_ir_utils import succ_deeper, succ_incoming, is_constant
from myia.clone import GraphCloner
from myia.debug.label import Index
from myia import primops


def test_clone_simple():
    def f(x, y):
        a = x * x
        b = y * y
        c = a + b
        return c

    g = parse(f)

    cl = GraphCloner(g, clone_constants=True)

    g2 = cl[g]

    d1 = set(dfs(g.return_, succ_deeper))
    d2 = set(dfs(g2.return_, succ_deeper))

    # Both node sets should be disjoint
    assert d1 & d2 == set()

    # Without cloning constants
    cl2 = GraphCloner(g, clone_constants=False)

    g2 = cl2[g]

    d1 = set(dfs(g.return_, succ_deeper))
    d2 = set(dfs(g2.return_, succ_deeper))

    common = d1 & d2
    assert all(is_constant(x) for x in common)
    assert {x.value for x in common} == {primops.add, primops.mul}


def test_clone_closure():
    def f(x, y):
        def j(z):
            a = x + y
            b = a + z
            return b
        c = j(3)
        return c

    parsed_f = parse(f)
    idx = Index(parsed_f)
    g = idx['j']

    cl = GraphCloner(g, clone_constants=True)
    idx2 = Index(cl[g], succ=succ_incoming)

    for name in 'xy':
        assert idx[name] is idx2[name]
    for name in 'zabj':
        assert idx[name] is not idx2[name]


def test_clone_scoping():
    def f(x, y):
        def g():
            # Depends on f, therefore cloned
            return x + y

        def h(z):
            # No dependency on f, so not nested and not cloned
            return z * z

        def i(q):
            # Depends on f, therefore cloned
            return g() * q
        return g() + h(x) + i(y)

    g = parse(f)

    cl = GraphCloner(g, clone_constants=True)

    g2 = cl[g]

    idx1 = Index(g)
    idx2 = Index(g2)

    for name in 'fgi':
        assert idx1[name] is not idx2[name]
    for name in 'h':
        assert idx1[name] is idx2[name]


def test_clone_total():
    def f1(x):
        return x * x

    def f2(y):
        return f1(y) + 3

    g = parse(f2)
    idx0 = Index(g)

    cl1 = GraphCloner(g, clone_constants=True, total=True)
    idx1 = Index(cl1[g])
    assert idx1['f2'] is not idx0['f2']
    assert idx1['f1'] is not idx0['f1']

    cl2 = GraphCloner(g, clone_constants=True, total=False)
    idx2 = Index(cl2[g])
    assert idx2['f2'] is not idx0['f2']
    assert idx2['f1'] is idx0['f1']


def test_clone_inline():
    def f(x, y):
        a = x * x
        b = y * y
        c = a + b
        return c

    g = parse(f)

    one = Constant(1)
    two = Constant(2)
    three = Constant(3)

    target = Graph()
    target.debug.name = 'target'
    target.output = three

    cl = GraphCloner(clone_constants=False)
    cl.add_clone(g, target, [one, two], False)

    # target does not actually replace g
    assert cl[g] is not target
    assert cl[g] is g

    new_root = cl[g.output]
    assert new_root is not g.output

    # Clone did not change target
    assert target.output is three

    nodes = set(dfs(new_root, succ_incoming))
    # Parameters should be replaced by these constants
    assert one in nodes
    assert two in nodes

    # Clones of g's nodes should belong to target
    orig_nodes = set(dfs(g.output, succ_incoming))
    assert all(cl[node].graph in {target, None}
               for node in orig_nodes
               if node.graph is g)
