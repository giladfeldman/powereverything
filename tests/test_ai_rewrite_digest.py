"""Rewrite transport preserves the confirmed source record without copying it."""
import pytest

from powerbench.provenance import input_hash
from powerbench.review.assistant import assistant_prompt, validate_assistance


def test_rewrite_can_attest_to_the_exact_confirmed_record_digest():
 confirmed={'canonical_paragraph':'Two independent groups required total N=200.','chronology':'unknown','effect_rationale':None}
 prompt=assistant_prompt('rewrite','Selected paragraph.',confirmed)
 digest=input_hash(confirmed)
 assert digest in prompt['prompt']
 result=validate_assistance('rewrite','Selected paragraph.',{'paragraph':'Two independent groups required total N=200. [effect rationale needed]','confirmed_sha256':digest},confirmed)
 assert result['confirmed']==confirmed
 for bad in [{'confirmed_sha256':'0'*64},{'confirmed_sha256':digest,'confirmed':{}}]:
  with pytest.raises(ValueError):validate_assistance('rewrite','Selected paragraph.',{'paragraph':'Two independent groups required total N=200. [effect rationale needed]',**bad},confirmed)
