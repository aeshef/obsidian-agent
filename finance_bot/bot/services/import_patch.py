"""Interpret edits as a constrained patch to an unsaved draft only."""
import copy
import json
from datetime import date
from decimal import Decimal, InvalidOperation
from bot.llm import LLMClient
from bot.config_loader import load_text_config

FIELDS = {"account", "occurred_at", "category", "amount", "description"}


def apply_patch(rows, patch):
    indices = patch.get("indices")
    values = patch.get("values")
    if not isinstance(indices, list) or not indices or not isinstance(values, dict) or not values:
        raise ValueError("empty_patch")
    if any(type(i) is not int or not 1 <= i <= len(rows) for i in indices):
        raise ValueError("invalid_indices")
    if not set(values) <= FIELDS: raise ValueError("invalid_fields")
    if "occurred_at" in values: date.fromisoformat(values["occurred_at"])
    if "amount" in values:
        try:
            amount=Decimal(str(values["amount"]))
        except InvalidOperation as exc:
            raise ValueError("invalid_amount") from exc
        if not amount.is_finite() or amount<=0: raise ValueError("invalid_amount")
    if any(not isinstance(v,(str,int,float)) for v in values.values()): raise ValueError("invalid_value")
    result=copy.deepcopy(rows)
    for i in indices:
        result[i-1].update(values)
        for key in list(result[i-1]):
            if key.startswith("_found_"): result[i-1].pop(key)
    return result


async def apply_patch_text(rows, instruction, user_id):
    from .nlu_parser import TransactionNLUParser
    context=await TransactionNLUParser()._get_user_context(user_id)
    from shared.tz import now_in_tz
    payload={"current_date":now_in_tz().date().isoformat(),"rows":[{k:v for k,v in r.items() if not k.startswith('_')} for r in rows],"instruction":instruction}
    patch=await LLMClient().chat_json(messages=[{"role":"system","content":load_text_config("import_patch")+context},{"role":"user","content":json.dumps(payload,ensure_ascii=False)}])
    return apply_patch(rows,patch)
