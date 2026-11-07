# Rule packs

Each subfolder is a rule pack: a `SKILL.md` (or any `.md`) of writing rules that is appended to
every agent's instructions as reference knowledge. The agents' own instructions take precedence
where they conflict (process, output files, never adding facts).

- `academic-humanizer/` — Academic Humanizer by AIScientists-Dev (MIT), verbatim.
- Add your own, e.g. `my-group/SKILL.md` with your group's conventions, and enable it in the
  review app (模型设置 → 规则包) or in `config/models.toml` → `[rules] packs`.
