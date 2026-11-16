"""The templates that the parity tests compare pybars_rs and pybars on.

* ``SEED_CORPUS``: templates that each pin down one pybars behaviour;
* ``random_template``: pieces of real templates and syntax errors, with a few
  characters inserted, deleted or replaced;
* ``NESTED_SHAPES``: the shapes whose nesting makes pybars recurse the most;
* ``BENCH_SIZES`` and ``ADVERSARIAL``: benchmark and complexity inputs.
"""

#: Characters that each grammar rule, CPython predicate or repr() branch tells apart.
PROBLEM_CHARACTERS = [
    *"\\{}[]()'\"=/.@#^&>!|-_~",
    *'\t\r\n\f\v\x00\x1f\x7f\x85',
    *'\u00a0\u2000\u200b\u2028\u3000',
    *'\u00b2\u0663\uff15\u0301\u0bcd\u2160\u00bc\u00aa',
    '\ud800',
    '\udfff',
    '\uffff',
    '\U0001f600',
    '\U0001fae9',  # printable from Unicode 16.0 (CPython 3.14)
    '\U0001e4f3',  # a decimal digit from Unicode 15.0 (CPython 3.12)
    '\U000e0001',
    '本文',
    'a',
    'Z',
    '0',
]

TEMPLATE_PIECES = [
    '{{name}}',
    '{{{name}}}',
    '{{&name}}',
    '{{a.b}}',
    '{{a/b}}',
    '{{../a}}',
    '{{@../a}}',
    '{{@index}}',
    '{{a.[b]}}',
    '{{a.[b.c]}}',
    '{{this}}',
    '{{foo ab=1}}',
    '{{foo ab="x"}}',
    "{{foo ab='y\\\\'}}",
    '{{foo ab=true}}',
    '{{foo ab=null}}',
    '{{foo ab=undefined}}',
    '{{foo ab=-12}}',
    '{{foo (bar)}}',
    '{{foo (bar baz=1)}}',
    '{{! comment }}',
    '{{!-- long comment --}}',
    '{{#if a}}x{{/if}}',
    '{{#if a}}x{{else}}y{{/if}}',
    '{{^if a}}x{{/if}}',
    '{{#each xs}}{{name}}{{/each}}',
    '{{> partial}}',
    '{{> partial arg}}',
    '{{> partial ab=1}}',
    '{{> partial ab=1 ab=2}}',
    '{{> partial ab=(missing) cd=1 ab=2}}',
    '{{> partial ab=(missing) [ab]=2}}',
    '{{> (dynamic) ab=1}}',
    '{{{{raw}}}}{{x}}{{{{/raw}}}}',
    # Whitespace control, and lines of block tags (pybars3 0.9.7).
    '{{~name}}',
    '{{name~}}',
    '{{~#if a~}}x{{~/if~}}',
    ' ~}}',
    '{{~',
    '\n{{#if a}}\n',
    '\n  {{/if}}  \n',
    '{{else}}\n',
    '\n{{else if b}}\n',
    '\t{{!note}}\t\r\n',
    # Order emails.
    '{{#if order.shipped}}Order {{order.id}} shipped to {{address.city}}{{/if}}',
    '{{#ifEquals user.role "admin"}}@admins{{/ifEquals}}',
    '{{^items}}Your cart is empty, see [the shop](https://example.com/shop){{/items}}',
    '{{format "price*2"}}',
    '{{#if order.gift}}\n**{{order.message.text}}**\n{{/if}}\n',
    'support@example.com @alice ',
    'text',
    '  ',
    '\t',
    '\n',
    '\r\n',
    'é',
    'a\r',
    '{{',
    '}}',
    '{{}}',
    '{{ }}',
    '{{#}}',
    '{{/}}',
    '{{!}}',
    '{{>}}',
    '{{a',
    'a}}',
    '{{#if}}{{/if}}',
    '{{#if a}}',
    '{{/if}}',
    '{{#if a}}{{#if b}}x{{/if}}{{/if}}',
    '{{foo a=1}}',
    '{{foo ab=}}',
    '{{foo =1}}',
    '{{foo ab==1}}',
]


def random_template(rng):
    """Join template pieces, then insert, delete or replace a few characters."""
    text = ''.join(rng.choice(TEMPLATE_PIECES) for _ in range(rng.randint(0, 8)))
    for _ in range(rng.randint(0, 3)):
        if not text:
            text = rng.choice(PROBLEM_CHARACTERS)
            continue
        operation = rng.random()
        position = rng.randrange(len(text) + 1)
        if operation < 0.4:
            text = text[:position] + rng.choice(PROBLEM_CHARACTERS) + text[position:]
        elif operation < 0.7:
            text = text[:position] + text[position + 1:]
        else:
            index = min(position, len(text) - 1)
            text = text[:index] + rng.choice(PROBLEM_CHARACTERS) + text[index + 1:]
    return text


#: Templates that each pin down one pybars behaviour (see docs/parity.md).
SEED_CORPUS = [
    '',
    'Hello {{name}}!',
    'hello {{name',
    'abc {{foo',
    'abc {{#if a}} xyz',
    '{{value}\nmore\nlines',
    'line1\nline2 {{/x}}\nline3',
    '{{#if\ta}}x{{/if}}',
    "{{foo ab='x\\\\y'}}",
    '{{a-b}}',
    '{{foo x=-12}}',
    '{{x}}\r\n',
    '\r\nx{{a}}\r\ny',
    '{{#if a}}x{{else}y{{/if}}',
    '{{#if a}}{{#if b}}{{#each xs}}{{name}}{{/each}}{{/if}}{{/if}}',
    '{{#if a}}x{{else}}y{{/if}}',
    '{{#if a}}x{{else}}{{/if}}',
    '{{^if a}}x{{/if}}',
    "{{> part ab=1 cd=resolve(context, u'x')}}",
    '{{> part a=1 b=2}}{{> part 1 2}}',
    '{{> part 1 2}}',
    '{{{{raw}}}}{{x}}{{{{/raw}}}}',
    '{{! comment }}{{!-- long --}}',
    '{{foo (bar (baz 1))}}',
    '{{foo (a.b x)}}',
    '{{foo -12}}',
    '{{foo a=1}}',
    '{{foo trueish}}',
    '{{foo 12abc}}',
    "{{a.[b'c]}}",
    '{{user.profile.[a.b.c.d}}',
    '{{[}}',
    'a\ud800b {{x}}',
    '{{x.[a\ud800]}}',
    '{{foo ²}}',
    '{{foo ٣}}',
    '{{foo -²12}}',
    '{{foo \U0001e4f3}}',
    '{{foo ' + '1' * 4301 + '}}',
    '{{foo ' + '0' * 4301 + '}}',
    '{{foo ' + '1' * 199 + '²}}',
    '{{his}}\r\n{{foo ab="x\ud800"}}',
    '{{#if a}}\nbody\n{{/if}}\n',
    '  {{#if a}}  \n  body\n  {{/if}}  \n',
    'text {{#if a}} y {{/if}} z',
    '{{^if a}}\nbody\n{{/if}}\n',
    '{{#if a}}\nx\n{{else}}\ny\n{{/if}}\n',
    '{{a_b}}{{a-b}}{{a@b}}',
    '{{this}}{{../a}}{{@../index}}',
    '{{> part aa=1 aa=2}}',
    '{{> part aa=(missing) bb=1 aa=2}}',
    '{{> part aa=(missing) [aa]=2}}',
    '{{> part é_1=v}}',
    '{{x.' + '[a' * 32 + ' }}',
    '{{x.[a\x00b]}}',
    'caf\u00e9 \u2028 \x85 \U0001f600 \U0001fae9 \U000e0001',
    '{{^if a}}' * 40 + 'x' + '{{/if}}' * 40,
    '{{foo ' + '(bar ' * 40 + 'a' + ')' * 40 + '}}',
    '{{#if a}}' * 19 + 'x' + '{{/if}}' * 19,
    '{{#if a}}' * 61 + 'x' + '{{/if}}' * 61,
    '{{#if order.shipped}}Order {{order.id}} for {{user.name}} shipped on {{order.date}}{{/if}}\n'
    '{{#ifEquals user.role "admin"}}admin{{else}}customer{{/ifEquals}}\n'
    '{{^gift}}Track it at https://example.com/track with {{carrier.name}}{{/gift}}\n',
    # Whitespace control, and lines of block tags (pybars3 0.9.7).
    'a {{~b~}} c',
    'a \t\n {{~b}}',
    '{{a~}}  \n b',
    '{{~~}}',
    'x\u3000{{~y}}\x85',
    'x\n{{#if a}}\ny\n{{/if}}\nz',
    'x\n  {{#a}} {{#b}} \r\ny{{/b}}{{/a}}',
    'x\n{{#if a}}\n{{else}}\ny{{/if}}',
    'x\n{{#a\nb}}\ny{{/a}}',
    '  {{#a}}  \nb{{/a}}',
    'a\n  {{/b}}  ',
    'a\n{{/b}}\n',
    'a\r\n{{/b}}\r\n',
    '{{#a}}\n{{! note }}\n{{/a}}\n',
    '{{a}}\n  {{~b}',
    'line1\n  {{~/x}}\nline3',
]


def nested_template(shape, depth):
    """A template of one of the steepest shapes, nested ``depth`` times."""
    return NESTED_SHAPES[shape](depth)


NESTED_SHAPES = {
    'blocks': lambda n: '{{#if a}}' * n + 'x' + '{{/if}}' * n,
    'else blocks': lambda n: '{{#if a}}x{{else}}' * n + 'y' + '{{/if}}' * n,
    'inverted blocks': lambda n: '{{^if a}}' * n + 'x' + '{{/if}}' * n,
    'standalone blocks': lambda n: '{{#if a}}\n' * n + 'x\n' + '{{/if}}\n' * n,
    'subexpressions': lambda n: '{{foo ' + '(bar ' * n + 'a' + ')' * n + '}}',
    'keyword subexpressions': lambda n: '{{foo ' + '(bar kk=' * n + 'a' + ')' * n + '}}',
    'partial name': lambda n: '{{> ' + '(bar ' * n + 'a' + ')' * n + '}}',
    'unclosed blocks': lambda n: '{{#if a}}' * n + 'x',
    'mixed': lambda n: '{{#each xs}}{{foo (bar (baz a))}}' * n + '{{/each}}' * n,
    'flat': lambda n: '{{a}} ' * n,
}


#: An order email template.
MESSAGE_TEMPLATE = (
    '{{#if order.shipped}}Order {{order.id}} shipped on {{order.date}} '
    'to {{address.street}}{{/if}}\n'
    '{{#if order.delayed}}Delayed with {{carrier.name}} ({{carrier.phone}}) until {{order.eta}}{{/if}}\n'
    '{{#if order.delivered}}Delivered to {{address.city}}{{/if}}\n'
    '{{^delivered}}Track it at https://example.com/track for {{carrier.name}} '
    'in {{address.country}}{{/delivered}}\n'
    '{{#if order.coupon.code}}coupon {{order.coupon.code}}{{else}}none{{/if}}\n'
)

BENCH_SIZES = {
    '100 B': MESSAGE_TEMPLATE[:100],
    '1.3 KB': MESSAGE_TEMPLATE * 3,
    '10 KB': (MESSAGE_TEMPLATE * 24)[:10_000],
    '50 KB': (MESSAGE_TEMPLATE * 120)[:50_000],
}

#: Inputs on which a PEG parser that rescans text is quadratic.
ADVERSARIAL = {
    'plain text': lambda n: 'x' * n,
    'open mustaches': lambda n: '{{' * (n // 2),
    'long bracket path': lambda n: '{{a.[' + 'b' * n + ']}}',
    'unmatched brackets': lambda n: '{{x.' + '[a' * (n // 2) + ' }}',
    'many else': lambda n: '{{#if a}}' + '{{else}}' * (n // 8) + '{{/if}}',
    'unterminated string': lambda n: '{{foo "' + 'x' * n,
    'many tags': lambda n: '{{a}}' * (n // 5),
    'whitespace run': lambda n: ' ' * n + 'x',
    'whitespace before a tilde': lambda n: ' ' * n + '{{~a}}',
    'lines of tags': lambda n: '\n{{#a}}' * (n // 7),
    'tilde tags': lambda n: '{{~a~}} ' * (n // 8),
}
