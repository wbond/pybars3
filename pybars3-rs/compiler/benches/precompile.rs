//! `cargo bench`: precompile order-email style templates of several sizes,
//! and inputs that a naive PEG implementation handles in quadratic time.

#![forbid(unsafe_code)]
#![allow(missing_docs)]

use std::hint::black_box;

use criterion::{BenchmarkId, Criterion, Throughput, criterion_group, criterion_main};
use pybars3_compiler::{Options, PybarsVersion, UnicodeVersion};

/// pybars3 0.9.7 on CPython 3.12.
const OPTIONS: Options = Options::new(PybarsVersion::V0_9_7, UnicodeVersion::V15_0);

/// An order email template.
const MESSAGE: &str = "{{#if order.shipped}}Order {{order.id}} shipped on {{order.date}} \
to {{address.street}}{{/if}}\n\
{{#if order.delayed}}Delayed with {{carrier.name}} ({{carrier.phone}}) until {{order.eta}}{{/if}}\n\
{{#if order.delivered}}Delivered to {{address.city}}{{/if}}\n\
{{^delivered}}Track it at https://example.com/track for {{carrier.name}} \
in {{address.country}}{{/delivered}}\n\
{{#if order.coupon.code}}coupon {{order.coupon.code}}{{else}}none{{/if}}\n";

fn sized(bytes: usize) -> String {
    let mut text = MESSAGE.repeat(bytes / MESSAGE.len() + 1);
    // Every byte of MESSAGE is ASCII.
    text.truncate(bytes);
    text
}

fn templates(c: &mut Criterion) {
    let mut group = c.benchmark_group("precompile");
    for (label, bytes) in [
        ("100B", 100),
        ("1.3KB", 1_300),
        ("10KB", 10_000),
        ("50KB", 50_000),
    ] {
        let source = sized(bytes);
        group.throughput(Throughput::Bytes(source.len() as u64));
        group.bench_with_input(BenchmarkId::from_parameter(label), &source, |b, source| {
            b.iter(|| pybars3_compiler::precompile(black_box(source), &OPTIONS));
        });
    }
    group.finish();
}

fn adversarial(c: &mut Criterion) {
    let n = 20_000;
    let cases = [
        ("plain text", "x".repeat(n)),
        ("open mustaches", "{{".repeat(n / 2)),
        (
            "long bracket path",
            format!("{{{{a.[{}]}}}}", "b".repeat(n)),
        ),
        (
            "unmatched brackets",
            format!("{{{{x.{} }}}}", "[a".repeat(n / 2)),
        ),
        (
            "many else",
            format!("{{{{#if a}}}}{}{{{{/if}}}}", "{{else}}".repeat(n / 8)),
        ),
        (
            "unterminated string",
            format!("{{{{foo \"{}", "x".repeat(n)),
        ),
        ("many tags", "{{a}}".repeat(n / 5)),
    ];
    let mut group = c.benchmark_group("adversarial");
    for (label, source) in &cases {
        group.throughput(Throughput::Bytes(source.len() as u64));
        group.bench_with_input(BenchmarkId::from_parameter(label), source, |b, source| {
            b.iter(|| pybars3_compiler::precompile(black_box(source), &OPTIONS));
        });
    }
    group.finish();
}

criterion_group!(benches, templates, adversarial);
criterion_main!(benches);
