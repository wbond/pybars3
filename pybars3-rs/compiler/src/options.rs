//! What pybars' output depends on: its own release, and properties of the
//! CPython interpreter that runs it.

use std::fmt;
use std::str::FromStr;

/// The pybars3 release whose compiler to reproduce.
///
/// pybars3 0.9.7 changed how whitespace is handled. pybars3 0.9.6 parses
/// the template and then removes the whitespace and newlines around block
/// tags that stand alone on their line, from the tree. pybars3 0.9.7 instead
/// rewrites the text before parsing it, with regular expressions: it adds
/// whitespace control (`{{~tag~}}`) and removes the lines that hold only
/// block tags. The two give different output for many templates, and the
/// generated module checks at run time that it runs on the pybars version it
/// was generated for.
///
/// The master branch of pybars3 has 0.9.7's compiler.
///
/// ```
/// use pybars3_compiler::PybarsVersion;
///
/// let version: PybarsVersion = "0.9.7".parse().unwrap();
/// assert_eq!(version, PybarsVersion::V0_9_7);
/// assert_eq!(version.to_string(), "0.9.7");
/// assert!(version.header().contains("if pybars.__version__ != '0.9.7':"));
/// assert!("0.9.5".parse::<PybarsVersion>().is_err());
/// ```
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord)]
#[non_exhaustive]
pub enum PybarsVersion {
    /// pybars3 0.9.6.
    V0_9_6,
    /// pybars3 0.9.7.
    V0_9_7,
}

impl PybarsVersion {
    /// Every supported release, oldest first.
    pub const ALL: [PybarsVersion; 2] = [PybarsVersion::V0_9_6, PybarsVersion::V0_9_7];

    /// The newest supported release. It changes when a release of this crate
    /// adds a pybars3 release, and so would the output of code that uses it.
    pub const LATEST: PybarsVersion = PybarsVersion::V0_9_7;

    /// The version as `pybars.__version__` spells it, such as `"0.9.7"`.
    #[must_use]
    pub const fn as_str(self) -> &'static str {
        match self {
            PybarsVersion::V0_9_6 => "0.9.6",
            PybarsVersion::V0_9_7 => "0.9.7",
        }
    }

    /// The text that every module generated for this release starts with:
    /// the header that pybars' `FunctionContainer.full_code` puts before the
    /// code of the `render` function. It names the release twice.
    #[must_use]
    pub const fn header(self) -> &'static str {
        crate::codegen::header(self)
    }
}

impl fmt::Display for PybarsVersion {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.as_str())
    }
}

/// The error of parsing an unsupported [`PybarsVersion`].
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct UnknownPybarsVersion(String);

impl fmt::Display for UnknownPybarsVersion {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "unsupported pybars3 version {:?}", self.0)
    }
}

impl std::error::Error for UnknownPybarsVersion {}

impl FromStr for PybarsVersion {
    type Err = UnknownPybarsVersion;

    /// Parse `pybars.__version__`, such as `"0.9.7"`.
    fn from_str(version: &str) -> Result<Self, Self::Err> {
        PybarsVersion::ALL
            .into_iter()
            .find(|candidate| candidate.as_str() == version)
            .ok_or_else(|| UnknownPybarsVersion(version.to_owned()))
    }
}

/// The version of CPython's Unicode database (`unicodedata.unidata_version`).
///
/// pybars classifies characters with `str.isalpha()`, `str.isdigit()` and
/// similar methods, and `repr()` escapes the characters that
/// `str.isprintable()` rejects. Their answers change from one Unicode
/// version to the next, and so does the code pybars generates for some
/// templates.
///
/// ```
/// use pybars3_compiler::UnicodeVersion;
///
/// let version: UnicodeVersion = "15.0.0".parse().unwrap();
/// assert_eq!(version, UnicodeVersion::V15_0);
/// assert_eq!(UnicodeVersion::for_cpython(3, 12), Some(version));
/// assert_eq!(version.to_string(), "15.0.0");
/// assert!("12.1.0".parse::<UnicodeVersion>().is_err());
/// ```
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord)]
#[non_exhaustive]
pub enum UnicodeVersion {
    /// Unicode 13.0.0, used by CPython 3.10.
    V13_0,
    /// Unicode 14.0.0, used by CPython 3.11.
    V14_0,
    /// Unicode 15.0.0, used by CPython 3.12.
    V15_0,
    /// Unicode 15.1.0, used by CPython 3.13.
    V15_1,
    /// Unicode 16.0.0, used by CPython 3.14.
    V16_0,
    /// Unicode 17.0.0, used by CPython 3.15.
    V17_0,
}

impl UnicodeVersion {
    /// Every supported version, oldest first.
    pub const ALL: [UnicodeVersion; 6] = [
        UnicodeVersion::V13_0,
        UnicodeVersion::V14_0,
        UnicodeVersion::V15_0,
        UnicodeVersion::V15_1,
        UnicodeVersion::V16_0,
        UnicodeVersion::V17_0,
    ];

    /// The newest supported version. It changes when a release adds a
    /// CPython version, and so would the output of code that uses it.
    pub const LATEST: UnicodeVersion = UnicodeVersion::V17_0;

    /// The Unicode database of CPython `major.minor`, if this crate has its
    /// tables. CPython keeps the version of its database for the whole life
    /// of a minor version.
    #[must_use]
    pub const fn for_cpython(major: u32, minor: u32) -> Option<Self> {
        match (major, minor) {
            (3, 10) => Some(UnicodeVersion::V13_0),
            (3, 11) => Some(UnicodeVersion::V14_0),
            (3, 12) => Some(UnicodeVersion::V15_0),
            (3, 13) => Some(UnicodeVersion::V15_1),
            (3, 14) => Some(UnicodeVersion::V16_0),
            (3, 15) => Some(UnicodeVersion::V17_0),
            _ => None,
        }
    }

    /// The version as `unicodedata.unidata_version` spells it, such as
    /// `"15.0.0"`.
    #[must_use]
    pub const fn as_str(self) -> &'static str {
        match self {
            UnicodeVersion::V13_0 => "13.0.0",
            UnicodeVersion::V14_0 => "14.0.0",
            UnicodeVersion::V15_0 => "15.0.0",
            UnicodeVersion::V15_1 => "15.1.0",
            UnicodeVersion::V16_0 => "16.0.0",
            UnicodeVersion::V17_0 => "17.0.0",
        }
    }

    /// The version's bit in the masks of the character tables.
    pub(crate) const fn bit(self) -> u8 {
        1 << (self as u8)
    }
}

impl fmt::Display for UnicodeVersion {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.as_str())
    }
}

/// The error of parsing an unsupported [`UnicodeVersion`].
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct UnknownUnicodeVersion(String);

impl fmt::Display for UnknownUnicodeVersion {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "unsupported Unicode version {:?}", self.0)
    }
}

impl std::error::Error for UnknownUnicodeVersion {}

impl FromStr for UnicodeVersion {
    type Err = UnknownUnicodeVersion;

    /// Parse `unicodedata.unidata_version`, such as `"15.0.0"`.
    fn from_str(version: &str) -> Result<Self, Self::Err> {
        UnicodeVersion::ALL
            .into_iter()
            .find(|candidate| candidate.as_str() == version)
            .ok_or_else(|| UnknownUnicodeVersion(version.to_owned()))
    }
}

/// What [`precompile`](crate::precompile) needs to know about the pybars it
/// reproduces, and about the CPython that runs it.
///
/// The pybars3 release and the Unicode version have no default, because the
/// generated code depends on them: pick the ones of the interpreter that will
/// run pybars.
///
/// ```
/// use pybars3_compiler::{Options, PybarsVersion, UnicodeVersion};
///
/// // pybars3 0.9.7 on CPython 3.12, with `sys.set_int_max_str_digits(0)`.
/// let options =
///     Options::new(PybarsVersion::V0_9_7, UnicodeVersion::V15_0).with_int_max_str_digits(0);
/// assert_eq!(options.pybars_version(), PybarsVersion::V0_9_7);
/// assert_eq!(options.unicode_version(), UnicodeVersion::V15_0);
/// assert_eq!(options.int_max_str_digits(), 0);
/// assert_eq!(options.nesting_limit(), Options::MAX_NESTING_LIMIT);
/// ```
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct Options {
    pybars_version: PybarsVersion,
    unicode_version: UnicodeVersion,
    int_max_str_digits: usize,
    nesting_limit: usize,
}

impl Options {
    /// CPython's default for `sys.get_int_max_str_digits()`.
    pub const DEFAULT_INT_MAX_STR_DIGITS: usize = 4300;

    /// The deepest nesting that the port compiles; see
    /// [`with_nesting_limit`](Options::with_nesting_limit).
    ///
    /// pybars itself reaches CPython's default recursion limit at about 50
    /// levels when it is called from a shallow stack.
    pub const MAX_NESTING_LIMIT: usize = 20;

    /// The options of this pybars3 release, on a CPython with this Unicode
    /// database at its default settings: `sys.get_int_max_str_digits()` is
    /// 4300, and nesting up to
    /// [`MAX_NESTING_LIMIT`](Options::MAX_NESTING_LIMIT) compiles.
    #[must_use]
    pub const fn new(pybars_version: PybarsVersion, unicode_version: UnicodeVersion) -> Self {
        Options {
            pybars_version,
            unicode_version,
            int_max_str_digits: Options::DEFAULT_INT_MAX_STR_DIGITS,
            nesting_limit: Options::MAX_NESTING_LIMIT,
        }
    }

    /// The limit of `int()` on the number of digits,
    /// `sys.get_int_max_str_digits()`; `0` means no limit.
    #[must_use]
    pub const fn with_int_max_str_digits(mut self, digits: usize) -> Self {
        self.int_max_str_digits = digits;
        self
    }

    /// The deepest nesting to compile; deeper templates return
    /// [`Fallback::NestingDepth`](crate::Fallback::NestingDepth).
    ///
    /// The template counts as one level, and every block body, `{{else}}`
    /// branch and subexpression inside it as one more. Values above
    /// [`MAX_NESTING_LIMIT`](Options::MAX_NESTING_LIMIT) are reduced to it,
    /// which bounds the native stack the port uses.
    ///
    /// ```
    /// use pybars3_compiler::{Error, Fallback, Options, PybarsVersion, UnicodeVersion};
    ///
    /// let options =
    ///     Options::new(PybarsVersion::V0_9_7, UnicodeVersion::V15_0).with_nesting_limit(1);
    /// assert_eq!(
    ///     pybars3_compiler::precompile("{{#if a}}x{{/if}}", &options),
    ///     Err(Error::Fallback(Fallback::NestingDepth)),
    /// );
    /// ```
    #[must_use]
    pub const fn with_nesting_limit(mut self, limit: usize) -> Self {
        self.nesting_limit = if limit < Options::MAX_NESTING_LIMIT {
            limit
        } else {
            Options::MAX_NESTING_LIMIT
        };
        self
    }

    /// The pybars3 release.
    #[must_use]
    pub const fn pybars_version(&self) -> PybarsVersion {
        self.pybars_version
    }

    /// The Unicode database version.
    #[must_use]
    pub const fn unicode_version(&self) -> UnicodeVersion {
        self.unicode_version
    }

    /// The limit on the digits of an integer literal (`0`: none).
    #[must_use]
    pub const fn int_max_str_digits(&self) -> usize {
        self.int_max_str_digits
    }

    /// The deepest nesting that compiles.
    #[must_use]
    pub const fn nesting_limit(&self) -> usize {
        self.nesting_limit
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn versions_round_trip_and_match_the_tables() {
        for (index, version) in UnicodeVersion::ALL.into_iter().enumerate() {
            assert_eq!(version.as_str().parse(), Ok(version));
            assert_eq!(version.to_string(), version.as_str());
            assert_eq!(crate::tables::VERSIONS[index], version.as_str());
            assert_eq!(version.bit(), 1 << index);
            let minor = 10 + u32::try_from(index).unwrap();
            assert_eq!(UnicodeVersion::for_cpython(3, minor), Some(version));
        }
        assert_eq!(crate::tables::VERSIONS.len(), UnicodeVersion::ALL.len());
        assert_eq!(UnicodeVersion::ALL.last(), Some(&UnicodeVersion::LATEST));
        assert_eq!(UnicodeVersion::for_cpython(3, 9), None);
        assert_eq!(UnicodeVersion::for_cpython(2, 7), None);
    }

    #[test]
    fn pybars_versions_round_trip() {
        for version in PybarsVersion::ALL {
            assert_eq!(version.as_str().parse(), Ok(version));
            assert_eq!(version.to_string(), version.as_str());
            let check = format!("if pybars.__version__ != '{version}':\n");
            assert!(version.header().contains(&check), "{version}");
        }
        assert_eq!(PybarsVersion::ALL.last(), Some(&PybarsVersion::LATEST));
        assert!(PybarsVersion::ALL.is_sorted());
    }

    #[test]
    fn unknown_versions_are_errors() {
        let error = "12.1.0".parse::<UnicodeVersion>().unwrap_err();
        assert_eq!(error.to_string(), "unsupported Unicode version \"12.1.0\"");
        let _: &dyn std::error::Error = &error;
        let error = "0.9.5".parse::<PybarsVersion>().unwrap_err();
        assert_eq!(error.to_string(), "unsupported pybars3 version \"0.9.5\"");
        let _: &dyn std::error::Error = &error;
    }

    #[test]
    fn the_nesting_limit_is_capped() {
        let options = Options::new(PybarsVersion::LATEST, UnicodeVersion::V15_0);
        assert_eq!(options.with_nesting_limit(5).nesting_limit(), 5);
        assert_eq!(
            options.with_nesting_limit(1000).nesting_limit(),
            Options::MAX_NESTING_LIMIT
        );
    }
}
