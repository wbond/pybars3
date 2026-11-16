//! `Compiler.clean_whitespace`: pybars3 0.9.6 drops the whitespace and
//! newline around block tags that stand alone on their line, from the parsed
//! tree. pybars3 0.9.7 replaced it with [`crate::whitespace_control`].
//!
//! This follows pybars' index arithmetic step by step, including what it does
//! not do: it looks at `block` items only (not inverted blocks), recurses
//! into their main template only (not `{{else}}` templates), and after a
//! close tag removes the whitespace but not the newline.

use crate::tree::{Item, Tag};

fn is(item: &Item, tag: Tag) -> bool {
    item.tag() == tag
}

/// Clean `tree`, a template list, in place.
pub(crate) fn clean_whitespace(tree: &mut Vec<Item>) {
    let mut pointer = 0;
    let mut end = tree.len();
    while pointer < end {
        if is(&tree[pointer], Tag::Block) {
            clean_block(tree, &mut pointer, &mut end);
        }
        pointer += 1;
    }
}

fn body(tree: &mut [Item], pointer: usize) -> &mut Vec<Item> {
    match &mut tree[pointer] {
        Item::Block(block) => &mut block.body,
        _ => unreachable!("clean_block is called on blocks"),
    }
}

fn clean_block(tree: &mut Vec<Item>, pointer: &mut usize, end: &mut usize) {
    // The open tag.
    let mut open_pre_whitespace = false;
    let mut open_pre_content = true;
    if *pointer > 1
        && is(&tree[*pointer - 1], Tag::Whitespace)
        && (is(&tree[*pointer - 2], Tag::Newline) || tree[*pointer - 2] == Item::Marker)
    {
        open_pre_whitespace = true;
        open_pre_content = false;
    } else if *pointer > 0
        && (is(&tree[*pointer - 1], Tag::Newline) || tree[*pointer - 1] == Item::Marker)
    {
        open_pre_content = false;
    }

    let child = body(tree, *pointer);
    let mut open_post_whitespace = false;
    let mut open_post_content = true;
    let child_len = child.len();
    if child_len > 2 && is(&child[1], Tag::Whitespace) && is(&child[2], Tag::Newline) {
        open_post_whitespace = true;
        open_post_content = false;
    } else if child_len > 1 && is(&child[1], Tag::Newline) {
        open_post_content = false;
    }

    if !open_pre_content && !open_post_content {
        if open_post_whitespace {
            child.remove(1);
        }
        child.remove(1); // the trailing newline
        if open_pre_whitespace {
            tree.remove(*pointer - 1);
            *pointer -= 1;
            *end -= 1;
        }
    }

    // The close tag.
    let child = body(tree, *pointer);
    let mut close_pre_whitespace = false;
    let mut close_pre_content = true;
    let child_len = child.len();
    if child_len > 2
        && is(&child[child_len - 1], Tag::Whitespace)
        && is(&child[child_len - 2], Tag::Newline)
    {
        close_pre_whitespace = true;
        close_pre_content = false;
    } else if child_len > 1 && is(&child[child_len - 1], Tag::Newline) {
        close_pre_content = false;
    }

    let mut close_post_whitespace = false;
    let mut close_post_content = true;
    let tree_len = tree.len();
    let p = *pointer;
    let followed_by = |offset: usize, tag| tree.get(p + offset).is_some_and(|item| is(item, tag));
    if (tree_len > p + 2 && followed_by(1, Tag::Whitespace) && followed_by(2, Tag::Newline))
        || (tree_len == p + 2 && followed_by(1, Tag::Whitespace))
    {
        close_post_whitespace = true;
        close_post_content = false;
    } else if (tree_len > p + 1 && followed_by(1, Tag::Newline)) || tree_len == p + 1 {
        close_post_content = false;
    }

    if !close_pre_content && !close_post_content {
        let child = body(tree, p);
        if close_pre_whitespace {
            child.pop();
        }
        child.pop(); // the preceding newline
        if close_post_whitespace {
            tree.remove(p + 1);
            *end -= 1;
        }
    }

    clean_whitespace(body(tree, p));
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::tree::Block;

    fn block(body: Vec<Item>) -> Item {
        Item::Block(Box::new(Block {
            inverted: false,
            symbol: "if".into(),
            args: vec![],
            body,
            alt: vec![],
        }))
    }

    #[test]
    fn a_standalone_block_loses_its_newlines() {
        let nl = || Item::Newline("\n".into());
        let mut tree = vec![
            Item::Marker,
            block(vec![Item::Marker, nl(), Item::Literal("x".into()), nl()]),
            nl(),
        ];
        clean_whitespace(&mut tree);
        let Item::Block(cleaned) = &tree[1] else {
            panic!("not a block")
        };
        assert_eq!(cleaned.body, vec![Item::Marker, Item::Literal("x".into())]);
        assert_eq!(tree.len(), 3, "the newline after the close tag stays");
    }
}
