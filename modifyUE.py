#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Patch openair2/RRC/NR_UE/rrc_UE.c NCR UE forwarding-rule telnet storage/printing logic.

Usage from the repository root:
  python3 fix_rrc_UE_ncr_telnet.py

Or specify the file explicitly:
  python3 fix_rrc_UE_ncr_telnet.py openair2/RRC/NR_UE/rrc_UE.c
"""

from __future__ import annotations

import pathlib
import re
import shutil
import sys
from datetime import datetime

DEFAULT_PATH = "openair2/RRC/NR_UE/rrc_UE.c"

GET_RULE_MACROS = "\n".join(f"NR_UE_NCR_DEFINE_GET_RULE_SET_CMD({i})" for i in range(64))
GET_RULE_CMD_ENTRIES = "\n".join(
    f'  {{"{i}", "show stored NCR forwarding rules with set={i}", nr_ue_ncr_telnet_get_forwarding_rule_set_{i}}},'
    for i in range(64)
)

NEW_NCR_BLOCK = f'''#define NR_UE_NCR_MAX_FORWARDING_RULES 64

typedef enum {{
  NR_UE_NCR_RULE_NONE = 0,
  NR_UE_NCR_RULE_PERIODIC,
  NR_UE_NCR_RULE_SEMI_PERSISTENT,
  NR_UE_NCR_RULE_APERIODIC
}} nr_ue_ncr_rule_type_t;

typedef struct {{
  bool valid;
  nr_ue_ncr_rule_type_t type;
  long set;
  long rsrc;
  long beam;
  long period;
  long offset;
  long sym;
  long dur;
  long ref_scs;
  long slot_offset;
  long beam_field_width;
  long number_of_fields;
}} nr_ue_ncr_forwarding_rule_t;

static nr_ue_ncr_forwarding_rule_t nr_ue_ncr_forwarding_rules[NR_UE_NCR_MAX_FORWARDING_RULES];
static pthread_mutex_t nr_ue_ncr_forwarding_rules_mutex = PTHREAD_MUTEX_INITIALIZER;
static pthread_mutex_t nr_ue_ncr_telnet_register_mutex = PTHREAD_MUTEX_INITIALIZER;
static bool nr_ue_ncr_telnet_registered = false;
static bool nr_ue_ncr_telnet_register_thread_started = false;

/*
 * add_telnetcmd() in this OAI branch rejects NULL var/cmd.
 * This dummy variable table is mandatory even when this module exposes commands only.
 */
static telnetshell_vardef_t nr_ue_ncr_telnet_vardef[] = {{
  {{"", 0, 0, NULL}}
}};

static const char *nr_ue_ncr_rule_type_to_string(nr_ue_ncr_rule_type_t type)
{{
  switch (type) {{
    case NR_UE_NCR_RULE_PERIODIC:
      return "periodic";
    case NR_UE_NCR_RULE_SEMI_PERSISTENT:
      return "semi_persistent";
    case NR_UE_NCR_RULE_APERIODIC:
      return "aperiodic";
    default:
      return "none";
  }}
}}

static nr_ue_ncr_forwarding_rule_t *nr_ue_ncr_find_forwarding_rule_locked(nr_ue_ncr_rule_type_t type, long set, long rsrc)
{{
  for (int i = 0; i < NR_UE_NCR_MAX_FORWARDING_RULES; i++) {{
    nr_ue_ncr_forwarding_rule_t *rule = &nr_ue_ncr_forwarding_rules[i];
    if (rule->valid && rule->type == type && rule->set == set && rule->rsrc == rsrc)
      return rule;
  }}
  return NULL;
}}

static nr_ue_ncr_forwarding_rule_t *nr_ue_ncr_alloc_forwarding_rule_locked(void)
{{
  for (int i = 0; i < NR_UE_NCR_MAX_FORWARDING_RULES; i++) {{
    if (!nr_ue_ncr_forwarding_rules[i].valid)
      return &nr_ue_ncr_forwarding_rules[i];
  }}
  return NULL;
}}

static void nr_ue_ncr_clear_forwarding_rules_by_type(nr_ue_ncr_rule_type_t type)
{{
  pthread_mutex_lock(&nr_ue_ncr_forwarding_rules_mutex);
  for (int i = 0; i < NR_UE_NCR_MAX_FORWARDING_RULES; i++) {{
    if (nr_ue_ncr_forwarding_rules[i].valid && nr_ue_ncr_forwarding_rules[i].type == type)
      memset(&nr_ue_ncr_forwarding_rules[i], 0, sizeof(nr_ue_ncr_forwarding_rules[i]));
  }}
  pthread_mutex_unlock(&nr_ue_ncr_forwarding_rules_mutex);
}}

static void nr_ue_ncr_clear_all_forwarding_rules(void)
{{
  pthread_mutex_lock(&nr_ue_ncr_forwarding_rules_mutex);
  memset(nr_ue_ncr_forwarding_rules, 0, sizeof(nr_ue_ncr_forwarding_rules));
  pthread_mutex_unlock(&nr_ue_ncr_forwarding_rules_mutex);
}}

static void nr_ue_ncr_store_periodic_forwarding_rule(long set,
                                                     long rsrc,
                                                     long beam,
                                                     long period,
                                                     long offset,
                                                     long sym,
                                                     long dur,
                                                     long ref_scs)
{{
  if (set < 0 || rsrc < 0) {{
    LOG_W(NR_RRC, "[NCR][UE] ignore periodic forwarding rule: invalid set=%ld rsrc=%ld\n", set, rsrc);
    return;
  }}

  pthread_mutex_lock(&nr_ue_ncr_forwarding_rules_mutex);
  nr_ue_ncr_forwarding_rule_t *rule = nr_ue_ncr_find_forwarding_rule_locked(NR_UE_NCR_RULE_PERIODIC, set, rsrc);
  if (!rule)
    rule = nr_ue_ncr_alloc_forwarding_rule_locked();
  if (!rule) {{
    pthread_mutex_unlock(&nr_ue_ncr_forwarding_rules_mutex);
    LOG_W(NR_RRC, "[NCR][UE] ignore periodic forwarding rule: rule table full\n");
    return;
  }}

  memset(rule, 0, sizeof(*rule));
  rule->valid = true;
  rule->type = NR_UE_NCR_RULE_PERIODIC;
  rule->set = set;
  rule->rsrc = rsrc;
  rule->beam = beam;
  rule->period = period;
  rule->offset = offset;
  rule->sym = sym;
  rule->dur = dur;
  rule->ref_scs = ref_scs;
  pthread_mutex_unlock(&nr_ue_ncr_forwarding_rules_mutex);
}}

static void nr_ue_ncr_store_semipersistent_forwarding_rule(long set,
                                                           long rsrc,
                                                           long beam,
                                                           long period,
                                                           long offset,
                                                           long sym,
                                                           long dur,
                                                           long ref_scs)
{{
  if (set < 0 || rsrc < 0) {{
    LOG_W(NR_RRC, "[NCR][UE] ignore semi-persistent forwarding rule: invalid set=%ld rsrc=%ld\n", set, rsrc);
    return;
  }}

  pthread_mutex_lock(&nr_ue_ncr_forwarding_rules_mutex);
  nr_ue_ncr_forwarding_rule_t *rule = nr_ue_ncr_find_forwarding_rule_locked(NR_UE_NCR_RULE_SEMI_PERSISTENT, set, rsrc);
  if (!rule)
    rule = nr_ue_ncr_alloc_forwarding_rule_locked();
  if (!rule) {{
    pthread_mutex_unlock(&nr_ue_ncr_forwarding_rules_mutex);
    LOG_W(NR_RRC, "[NCR][UE] ignore semi-persistent forwarding rule: rule table full\n");
    return;
  }}

  memset(rule, 0, sizeof(*rule));
  rule->valid = true;
  rule->type = NR_UE_NCR_RULE_SEMI_PERSISTENT;
  rule->set = set;
  rule->rsrc = rsrc;
  rule->beam = beam;
  rule->period = period;
  rule->offset = offset;
  rule->sym = sym;
  rule->dur = dur;
  rule->ref_scs = ref_scs;
  pthread_mutex_unlock(&nr_ue_ncr_forwarding_rules_mutex);
}}

static void nr_ue_ncr_store_aperiodic_forwarding_rule(long rsrc,
                                                       long slot_offset,
                                                       long sym,
                                                       long dur,
                                                       long ref_scs,
                                                       long beam_field_width,
                                                       long number_of_fields)
{{
  if (rsrc < 0) {{
    LOG_W(NR_RRC, "[NCR][UE] ignore aperiodic forwarding rule: invalid rsrc=%ld\n", rsrc);
    return;
  }}

  pthread_mutex_lock(&nr_ue_ncr_forwarding_rules_mutex);
  nr_ue_ncr_forwarding_rule_t *rule = nr_ue_ncr_find_forwarding_rule_locked(NR_UE_NCR_RULE_APERIODIC, -1, rsrc);
  if (!rule)
    rule = nr_ue_ncr_alloc_forwarding_rule_locked();
  if (!rule) {{
    pthread_mutex_unlock(&nr_ue_ncr_forwarding_rules_mutex);
    LOG_W(NR_RRC, "[NCR][UE] ignore aperiodic forwarding rule: rule table full\n");
    return;
  }}

  memset(rule, 0, sizeof(*rule));
  rule->valid = true;
  rule->type = NR_UE_NCR_RULE_APERIODIC;
  rule->set = -1;
  rule->rsrc = rsrc;
  rule->slot_offset = slot_offset;
  rule->sym = sym;
  rule->dur = dur;
  rule->ref_scs = ref_scs;
  rule->beam_field_width = beam_field_width;
  rule->number_of_fields = number_of_fields;
  pthread_mutex_unlock(&nr_ue_ncr_forwarding_rules_mutex);
}}

static int nr_ue_ncr_count_forwarding_rules_locked(void)
{{
  int count = 0;
  for (int i = 0; i < NR_UE_NCR_MAX_FORWARDING_RULES; i++) {{
    if (nr_ue_ncr_forwarding_rules[i].valid)
      count++;
  }}
  return count;
}}

static void nr_ue_ncr_telnet_print_one_rule(telnet_printfunc_t prnt, const nr_ue_ncr_forwarding_rule_t *rule)
{{
  if (!rule || !rule->valid)
    return;

  if (rule->type == NR_UE_NCR_RULE_APERIODIC) {{
    prnt("{{\"type\":\"%s\",\"rsrc\":%ld,\"slot_offset\":%ld,\"sym\":%ld,\"dur\":%ld,\"ref_scs\":%ld,\"beam_field_width\":%ld,\"number_of_fields\":%ld}}\n",
         nr_ue_ncr_rule_type_to_string(rule->type),
         rule->rsrc,
         rule->slot_offset,
         rule->sym,
         rule->dur,
         rule->ref_scs,
         rule->beam_field_width,
         rule->number_of_fields);
  }} else {{
    prnt("{{\"type\":\"%s\",\"set\":%ld,\"rsrc\":%ld,\"beam\":%ld,\"period\":%ld,\"offset\":%ld,\"sym\":%ld,\"dur\":%ld,\"ref_scs\":%ld}}\n",
         nr_ue_ncr_rule_type_to_string(rule->type),
         rule->set,
         rule->rsrc,
         rule->beam,
         rule->period,
         rule->offset,
         rule->sym,
         rule->dur,
         rule->ref_scs);
  }}
}}

static int nr_ue_ncr_telnet_get_forwarding_rule_all(char *buff, int debug, telnet_printfunc_t prnt)
{{
  (void)buff;
  (void)debug;

  pthread_mutex_lock(&nr_ue_ncr_forwarding_rules_mutex);
  const int count = nr_ue_ncr_count_forwarding_rules_locked();
  prnt("{{\"ok\":true,\"count\":%d}}\n", count);
  for (int i = 0; i < NR_UE_NCR_MAX_FORWARDING_RULES; i++) {{
    if (nr_ue_ncr_forwarding_rules[i].valid)
      nr_ue_ncr_telnet_print_one_rule(prnt, &nr_ue_ncr_forwarding_rules[i]);
  }}
  pthread_mutex_unlock(&nr_ue_ncr_forwarding_rules_mutex);
  return 0;
}}

static int nr_ue_ncr_telnet_get_forwarding_rule_by_set(long set, telnet_printfunc_t prnt)
{{
  if (set < 0) {{
    prnt("{{\"ok\":false,\"error\":\"bad_set\",\"set\":%ld,\"count\":0}}\n", set);
    return 0;
  }}

  int count = 0;
  pthread_mutex_lock(&nr_ue_ncr_forwarding_rules_mutex);
  for (int i = 0; i < NR_UE_NCR_MAX_FORWARDING_RULES; i++) {{
    if (nr_ue_ncr_forwarding_rules[i].valid && nr_ue_ncr_forwarding_rules[i].set == set)
      count++;
  }}

  if (count == 0) {{
    pthread_mutex_unlock(&nr_ue_ncr_forwarding_rules_mutex);
    prnt("{{\"ok\":false,\"error\":\"not_found\",\"set\":%ld,\"count\":0}}\n", set);
    return 0;
  }}

  prnt("{{\"ok\":true,\"set\":%ld,\"count\":%d}}\n", set, count);
  for (int i = 0; i < NR_UE_NCR_MAX_FORWARDING_RULES; i++) {{
    if (nr_ue_ncr_forwarding_rules[i].valid && nr_ue_ncr_forwarding_rules[i].set == set)
      nr_ue_ncr_telnet_print_one_rule(prnt, &nr_ue_ncr_forwarding_rules[i]);
  }}
  pthread_mutex_unlock(&nr_ue_ncr_forwarding_rules_mutex);
  return 0;
}}

#define NR_UE_NCR_DEFINE_GET_RULE_SET_CMD(_set) \\
  static int nr_ue_ncr_telnet_get_forwarding_rule_set_##_set(char *buff, int debug, telnet_printfunc_t prnt) \\
  {{ \\
    (void)buff; \\
    (void)debug; \\
    return nr_ue_ncr_telnet_get_forwarding_rule_by_set((_set), prnt); \\
  }}

{GET_RULE_MACROS}

static telnetshell_cmddef_t nr_ue_ncr_get_forwarding_rule_cmds[] = {{
  {{"all", "show all stored NCR forwarding rules", nr_ue_ncr_telnet_get_forwarding_rule_all}},
{GET_RULE_CMD_ENTRIES}
  {{"", "", NULL}}
}};

static bool nr_ue_ncr_try_register_get_forwarding_rule_telnet_cmd(void)
{{
  pthread_mutex_lock(&nr_ue_ncr_telnet_register_mutex);
  if (nr_ue_ncr_telnet_registered) {{
    pthread_mutex_unlock(&nr_ue_ncr_telnet_register_mutex);
    return true;
  }}

  add_telnetcmd_func_t addcmd = (add_telnetcmd_func_t)get_shlibmodule_fptr("telnetsrv", TELNET_ADDCMD_FNAME);
  if (addcmd == NULL) {{
    pthread_mutex_unlock(&nr_ue_ncr_telnet_register_mutex);
    return false;
  }}

  int rc = addcmd("getForwardingRule", nr_ue_ncr_telnet_vardef, nr_ue_ncr_get_forwarding_rule_cmds);
  if (rc == 0) {{
    nr_ue_ncr_telnet_registered = true;
    pthread_mutex_unlock(&nr_ue_ncr_telnet_register_mutex);
    LOG_I(NR_RRC, "[NCR][UE] Telnet command registered: getForwardingRule all | <set>\n");
    return true;
  }}

  pthread_mutex_unlock(&nr_ue_ncr_telnet_register_mutex);
  LOG_W(NR_RRC, "[NCR][UE] add_telnetcmd failed: getForwardingRule rc=%d\n", rc);
  return false;
}}

static void *nr_ue_ncr_telnet_register_thread(void *arg)
{{
  (void)arg;
  for (int i = 0; i < 200; i++) {{
    if (nr_ue_ncr_try_register_get_forwarding_rule_telnet_cmd())
      return NULL;
    usleep(100000);
  }}
  LOG_W(NR_RRC, "[NCR][UE] Telnet command registration failed after retry: getForwardingRule\n");
  return NULL;
}}

static void nr_ue_ncr_start_telnet_register_thread(void)
{{
  pthread_mutex_lock(&nr_ue_ncr_telnet_register_mutex);
  if (nr_ue_ncr_telnet_registered || nr_ue_ncr_telnet_register_thread_started) {{
    pthread_mutex_unlock(&nr_ue_ncr_telnet_register_mutex);
    return;
  }}
  nr_ue_ncr_telnet_register_thread_started = true;
  pthread_mutex_unlock(&nr_ue_ncr_telnet_register_mutex);

  pthread_t tid;
  int rc = pthread_create(&tid, NULL, nr_ue_ncr_telnet_register_thread, NULL);
  if (rc == 0) {{
    pthread_detach(tid);
  }} else {{
    LOG_W(NR_RRC, "[NCR][UE] failed to create telnet register thread: rc=%d\n", rc);
    pthread_mutex_lock(&nr_ue_ncr_telnet_register_mutex);
    nr_ue_ncr_telnet_register_thread_started = false;
    pthread_mutex_unlock(&nr_ue_ncr_telnet_register_mutex);
  }}
}}
'''


def replace_once(text: str, pattern: str, replacement: str, flags: int = 0, label: str = "") -> tuple[str, int]:
    new_text, n = re.subn(pattern, replacement, text, count=1, flags=flags)
    if n != 1:
        raise RuntimeError(f"replace failed: {label or pattern}")
    return new_text, n


def main() -> int:
    path = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PATH)
    if not path.exists():
        print(f"ERROR: file not found: {path}", file=sys.stderr)
        return 1

    text = path.read_text(encoding="utf-8", errors="surrogateescape")
    original = text

    # 1) Remove the old fixed-string telnet registration block that always returns No Rule.
    #    It is before the real nr_ue_ncr_* implementation and registers the same command name first.
    text, _ = replace_once(
        text,
        r"\n?static int ue_ncr_telnet_get_forwarding_rule_all_cmd\(char \*cmdbuff, int debug, telnet_printfunc_t prnt\).*?#define NR_UE_NCR_MAX_FORWARDING_RULES 64",
        "\n#define NR_UE_NCR_MAX_FORWARDING_RULES 64",
        flags=re.S,
        label="remove old No Rule getForwardingRule telnet block",
    )

    # 2) Replace the full NCR UE rule table / telnet command block with a key-safe version.
    text, _ = replace_once(
        text,
        r"#define NR_UE_NCR_MAX_FORWARDING_RULES 64.*?/\* NAS Attach request with IMSI \*/",
        NEW_NCR_BLOCK + "\n/* NAS Attach request with IMSI */",
        flags=re.S,
        label="replace NCR forwarding-rule storage and telnet block",
    )

    # 3) Remove the early registration call that registered the old fixed No Rule command.
    text = re.sub(r"\n\s*ue_ncr_telnet_register_cmds\(\);", "", text, count=1)

    # 4) Update old aperiodic store calls if the previous code passed fake set=rsrc, rsrc=rsrc.
    #    This regex intentionally only targets calls with duplicated first two arguments.
    text = re.sub(
        r"nr_ue_ncr_store_aperiodic_forwarding_rule\(\s*([^,;]+?)\s*,\s*\1\s*,",
        r"nr_ue_ncr_store_aperiodic_forwarding_rule(\1,",
        text,
        flags=re.S,
    )

    # 5) Optional safety: when obvious NCR release logs exist in the local file, clear stale rules.
    #    These substitutions are guarded; they do nothing if the exact log text is not present.
    text = text.replace(
        'LOG_I(NR_RRC, "[NCR][UE] NCR-FwdConfig RELEASE\\n");\n  return;',
        'LOG_I(NR_RRC, "[NCR][UE] NCR-FwdConfig RELEASE\\n");\n  nr_ue_ncr_clear_all_forwarding_rules();\n  return;',
    )
    text = text.replace(
        'LOG_I(NR_RRC, "[NCR][UE] AperiodicCfg RELEASE\\n");',
        'LOG_I(NR_RRC, "[NCR][UE] AperiodicCfg RELEASE\\n");\n      nr_ue_ncr_clear_forwarding_rules_by_type(NR_UE_NCR_RULE_APERIODIC);',
    )
    text = text.replace(
        'LOG_I(NR_RRC, "[NCR][UE] PeriodicCfg RELEASE\\n");',
        'LOG_I(NR_RRC, "[NCR][UE] PeriodicCfg RELEASE\\n");\n      nr_ue_ncr_clear_forwarding_rules_by_type(NR_UE_NCR_RULE_PERIODIC);',
    )
    text = text.replace(
        'LOG_I(NR_RRC, "[NCR][UE] SemiPersistentCfg RELEASE\\n");',
        'LOG_I(NR_RRC, "[NCR][UE] SemiPersistentCfg RELEASE\\n");\n      nr_ue_ncr_clear_forwarding_rules_by_type(NR_UE_NCR_RULE_SEMI_PERSISTENT);',
    )

    if text == original:
        print("ERROR: no changes made; file layout may differ from the expected branch.", file=sys.stderr)
        return 1

    backup = path.with_suffix(path.suffix + ".bak." + datetime.now().strftime("%Y%m%d%H%M%S"))
    shutil.copy2(path, backup)
    path.write_text(text, encoding="utf-8", errors="surrogateescape")

    print(f"OK: patched {path}")
    print(f"Backup: {backup}")
    print("Changed: removed old fixed No Rule telnet command, replaced NCR rule storage with type/set/rsrc keyed table, and kept one getForwardingRule registration path.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

