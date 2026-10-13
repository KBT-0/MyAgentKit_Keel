# LLM kod inceleme prompt'ları ve kural dosyaları: yayımlanmış metinler

Tarih: 2026-10-13. Amaç: uygulayıcıların ve satıcıların LLM incelemecilere verdiği prompt ve kural dosyalarının **kendi metni**. Etiketler: R = resmi doküman, B = mühendislik blogu (ölçümlü), P = makale, S = ikincil/topluluk. İngilizce alıntılar olduğu gibi bırakıldı; "..." ile kısaltma yok, satır kırılımları kaynaktaki gibi.

Ham dosyalar (curl ile indirilenler) şurada: `scratchpad/dl/` (codex_gist.md, anthropic_plugin.md, superpowers_reviewer.md, ecc_reviewer.md, cloudflare.html, bugbot.html).

---

## 0. Kaynakların kısa tanıtımı

| # | Kaynak | Tarih | Etiket | Ne tür metin |
|---|--------|-------|--------|--------------|
| 1 | Anthropic, Claude Code "Code Review" dokümanı | erişim 2026-10-13 | R | REVIEW.md şablonu, örnek kurallar, severity, effort |
| 2 | Anthropic, Claude Code "Best practices" | erişim 2026-10-13 | R | adversarial review subagent prompt'u, security-reviewer agent |
| 3 | Anthropic, `plugins/code-review/commands/code-review.md` (GitHub) | erişim 2026-10-13 | R | resmi plugin'in tam komut prompt'u |
| 4 | OpenAI Codex, GitHub code review dokümanı (learn.chatgpt.com) | erişim 2026-10-13 | R | P0/P1 kuralı, AGENTS.md `## Code Review Rules` |
| 5 | OpenAI Codex `codex-rs/core/review_prompt.md` (gist kopyası) | 2025 | S (resmi dosyanın kopyası) | `/review` sistem prompt'unun tam metni |
| 6 | OpenAI Cookbook "Build Code Review with the Codex SDK" | erişim 2026-10-13 | R | SDK incelemeci prompt'u + JSON şema |
| 7 | Cloudflare "Orchestrating AI code review at scale" | 2026-04 | B | security reviewer prompt'u, severity, re-review kuralları, rakamlar |
| 8 | Cursor "Building Bugbot" | 2026-02 | B | prompt dersleri, doğrulayıcı, resolution rate |
| 9 | Cursor Bugbot dokümanı (`.cursor/BUGBOT.md`, rules) | erişim 2026-10-13 | R | kural örnekleri, limitler |
| 10 | Greptile config reference + custom standards | erişim 2026-10-13 | R | greptile.json kural örnekleri, strictness |
| 11 | CodeRabbit path instructions + configuration reference | erişim 2026-10-13 | R | `.coderabbit.yaml` örnekleri, profile tanımları |
| 12 | cubic custom context | erişim 2026-10-13 | R | instructions, context dosyaları |
| 13 | GitHub Copilot "Customize code review" + "Use code review" | erişim 2026-10-13 (changelog 2025-06-13, 2025-09-03) | R | copilot-instructions.md örneği, 4.000 karakter limiti, desteklenmeyen talimatlar |
| 14 | Devin Review dokümanı | erişim 2026-10-13 | R | REVIEW.md örneği, severity sınıfları |
| 15 | obra/superpowers `code-reviewer.md` | erişim 2026-10-13 | S | topluluk reviewer prompt şablonu (tam) |
| 16 | affaan-m/everything-claude-code `agents/code-reviewer.md` | erişim 2026-10-13 | S | >80% güven kapısı, false-positive listesi |
| 17 | agentpedia.codes Codex AGENTS.md örneği | 2026 | S | `## Code Review Rules` örnek blokları |
| 18 | open-agent-security/openaca PR #210 | 2026 | S | P0-P3 listesinin P2 gürültüsü yarattığı gözlemi |
| 19 | melodic-software/standards PR #668 | 2026 | S | işaretçi-tek (pointer-only) Code Review Rules bölümü |
| 20 | DataCamp Claude Code Review tutorial | 2026 | S | REVIEW.md örneği, `/code-review` çıktı biçimi |
| 21 | Qiu & Gill, "Adversarial Review" arXiv 2608.18167 | 2026-08-16 | P | reviewer/critic prompt'ları, üç-verdict kısıtı, F1 |
| 22 | Jin & Chen, arXiv 2603.00539 "Are LLMs Reliable Code Reviewers?" | 2026-03 | P | prompt ayrıntısı arttıkça yanlış ret artıyor |
| 23 | SWR-Bench arXiv 2509.01494 | 2025-09 | P | 1000 PR benchmark, çoklu-inceleme toplama |

---

## 1. Kaynak kaynak alıntılar

### 1.1 Anthropic Claude Code "Code Review" (R) — https://code.claude.com/docs/en/code-review

Severity tablosu (hosted Code Review):

> | Marker | Severity | Meaning |
> | 🔴 | Important | A bug that should be fixed before merging |
> | 🟡 | Nit | A minor issue, worth fixing but not blocking |
> | 🟣 | Pre-existing | A bug that exists in the codebase but was not introduced by this PR |

Pipeline tanımı:

> "multiple agents analyze the diff and surrounding code in parallel on Anthropic infrastructure. Each agent looks for a different class of issue, then a verification step checks candidates against actual code behavior to filter out false positives. The results are deduplicated, ranked by severity, and posted as inline comments"

> "By default, Code Review focuses on correctness: bugs that would break production, not formatting preferences or missing test coverage."

CLAUDE.md ile REVIEW.md farkı:

> "**`CLAUDE.md`**: shared project instructions that Claude Code uses for all tasks, not just reviews. Code Review reads it as project context and flags newly introduced violations as nits."
> "**`REVIEW.md`**: review-only instructions, given to the agents that find and verify findings and consulted by the agents that rank and report them. Use it to say what your team wants flagged, at what severity, and how findings are reported."

"What you can tune" bölümünün her maddesi (tam):

> "**Severity**: redefine what 🔴 Important means for your repo. The default calibration targets production code; a docs repo, a config repo, or a prototype might want a much narrower definition. State explicitly which classes of finding are Important and which are Nit at most. You can also escalate in the other direction, for example treating any `CLAUDE.md` violation as Important rather than the default nit."

> "**Nit volume**: cap how many 🟡 Nit comments a single review posts. Prose and config files can be polished forever. A cap like "report at most five nits, mention the rest as a count in the summary" keeps reviews actionable."

> "**Skip rules**: list paths, branch patterns, and finding categories where Claude should post no findings. Common candidates are generated code, lockfiles, vendored dependencies, and machine-authored branches, along with anything your CI already enforces like linting or spellcheck. For paths that warrant some review but not full scrutiny, set a higher bar instead of skipping entirely: "in `scripts/`, only report if near-certain and severe.""

> "**Repo-specific checks**: add rules you want flagged on every PR, like "new API routes must have an integration test." Because `REVIEW.md` reaches every finding and verification agent directly, these land more reliably than the same rules in a long `CLAUDE.md`."

> "**Verification bar**: require evidence before a class of finding is posted. For example, "behavior claims need a `file:line` citation in the source, not an inference from naming" cuts false positives that would otherwise cost the author a round trip."

> "**Re-review convergence**: tell Claude how to behave when a PR has already been reviewed. A rule like "after the first review, suppress new nits and post Important findings only" stops a one-line fix from reaching round seven on style alone."

> "**Summary shape**: ask for the review body to open with a one-line tally such as `2 factual, 4 style`, and to lead with "no factual issues" when that's the case. The author wants to know the shape of the work before the details."

Resmi REVIEW.md örneği (tam):

```markdown
# Review instructions

## What Important means here

Reserve Important for findings that would break behavior, leak data,
or block a rollback: incorrect logic, unscoped database queries, PII
in logs or error messages, and migrations that aren't backward
compatible. Style, naming, and refactoring suggestions are Nit at
most.

## Cap the nits

Report at most five Nits per review. If you found more, say "plus N
similar items" in the summary instead of posting them inline. If
everything you found is a Nit, lead the summary with "No blocking
issues."

## Do not report

- Anything CI already enforces: lint, formatting, type errors
- Generated files under `src/gen/` and any `*.lock` file
- Test-only code that intentionally violates production rules

## Always check

- New API routes have an integration test
- Log lines don't include email addresses, user IDs, or request bodies
- Database queries are scoped to the caller's tenant
```

Uzunluk uyarısı:

> "Length has a cost: a long `REVIEW.md` dilutes the rules that matter most. Keep it to instructions that change review behavior, and leave general project context in `CLAUDE.md`."

Yerel `/code-review` ve effort:

> "Pass an [effort level] to trade coverage for confidence. At `low`, the review reports the findings it's most confident in, so you see fewer false positives. From `medium` through `max`, the review broadens coverage."

> "`--max-findings <n>`, `--max-findings all`, or `--max-findings default`: reports up to `n` findings, or every finding with `all`, in place of the review's usual limit."

> "The review follows your `CLAUDE.md` like any Claude Code session, but it doesn't read [`REVIEW.md`]."

Geri bildirim: her yoruma 👍/👎 eklenir; "Anthropic collects reaction counts after the PR merges and uses them to tune the reviewer." Maliyet: "Each review averages $15-25 in cost"; süre "completing in 20 minutes on average". Check run her zaman neutral: "The check run always completes with a neutral conclusion so it never blocks merging".

Ne yapar: Hosted serviste üç seviyeli severity, varsayılan odak correctness; REVIEW.md serbest markdown olup bul/doğrula/sırala ajanlarının hepsine gider; etkili olduğu söylenen 7 ayar kategorisi belgelenmiş.

### 1.2 Anthropic "Best practices" (R) — https://code.claude.com/docs/en/best-practices

Adversarial review bölümü:

> "Before treating a task as done, have a subagent review the diff in a fresh context and report gaps."

> "A reviewer running in a fresh [subagent] context sees only the diff and the criteria you give it, not the reasoning that produced the change, so it evaluates the result on its own terms."

Örnek prompt (tam):

```text
Use a subagent to review the rate limiter diff against PLAN.md. Check that
every requirement is implemented, the listed edge cases have tests, and
nothing outside the task's scope changed. Report gaps, not style preferences.
```

Callout (gürültü uyarısı, tam):

> "A reviewer prompted to find gaps will usually report some, even when the work is sound, because that is what it was asked to do. Chasing every finding leads to over-engineering: extra abstraction layers, defensive code, and tests for cases that can't happen. Tell the reviewer to flag only gaps that affect correctness or the stated requirements, and treat the rest as optional."

Writer/Reviewer oturum örneği:

> "Review the rate limiter implementation in @src/middleware/rateLimiter.ts. Look for edge cases, race conditions, and consistency with our existing middleware patterns."

Örnek security-reviewer subagent dosyası (tam):

```markdown
---
name: security-reviewer
description: Reviews code for security vulnerabilities
tools: Read, Grep, Glob, Bash
model: opus
---
You are a senior security engineer. Review code for:
- Injection vulnerabilities (SQL, XSS, command injection)
- Authentication and authorization flaws
- Secrets or credentials in code
- Insecure data handling

Provide specific line references and suggested fixes.
```

CLAUDE.md uzunluk kuralı: "Keep it concise. For each line, ask: *"Would removing this cause Claude to make mistakes?"* If not, cut it. Bloated CLAUDE.md files cause Claude to ignore your actual instructions!"

Ne yapar: Resmi tavsiye, incelemeciyi plana karşı çalıştırmak ve "gaps, not style" demek; bulgu üretme eğilimine karşı "only gaps that affect correctness or the stated requirements".

### 1.3 Anthropic resmi plugin `code-review.md` (R) — https://github.com/anthropics/claude-code/blob/main/plugins/code-review/commands/code-review.md

Ham dosya ~7.3 KB (`dl/anthropic_plugin.md`). Çekirdek kurallar:

Eleme kapısı (haiku ajan):

> "Launch a haiku agent to check if any of the following are true:
>    - The pull request is closed
>    - The pull request is a draft
>    - The pull request does not need code review (e.g. automated PR, trivial change that is obviously correct)
>    - Claude has already commented on this PR (check `gh pr view <PR> --comments` for comments left by claude)
>
>    If any condition is true, stop and do not proceed.
>
> Note: Still review Claude generated PR's."

Dört paralel ajan:

> "Agents 1 + 2: CLAUDE.md compliance sonnet agents
>    Audit changes for CLAUDE.md compliance in parallel. Note: When evaluating CLAUDE.md compliance for a file, you should only consider CLAUDE.md files that share a file path with the file or parents.
>
>    Agent 3: Opus bug agent (parallel subagent with agent 4)
>    Scan for obvious bugs. Focus only on the diff itself without reading extra context. Flag only significant bugs; ignore nitpicks and likely false positives. Do not flag issues that you cannot validate without looking at context outside of the git diff.
>
>    Agent 4: Opus bug agent (parallel subagent with agent 3)
>    Look for problems that exist in the introduced code. This could be security issues, incorrect logic, etc. Only look for issues that fall within the changed code."

Sinyal eşiği (tam):

> "**CRITICAL: We only want HIGH SIGNAL issues.** Flag issues where:
>    - The code will fail to compile or parse (syntax errors, type errors, missing imports, unresolved references)
>    - The code will definitely produce wrong results regardless of inputs (clear logic errors)
>    - Clear, unambiguous CLAUDE.md violations where you can quote the exact rule being broken
>
>    Do NOT flag:
>    - Code style or quality concerns
>    - Potential issues that depend on specific inputs or state
>    - Subjective suggestions or improvements
>
>    If you are not certain an issue is real, do not flag it. False positives erode trust and waste reviewer time."

Doğrulama adımı:

> "For each issue found in the previous step by agents 3 and 4, launch parallel subagents to validate the issue. [...] The agent's job is to review the issue to validate that the stated issue is truly an issue with high confidence."
> "Filter out any issues that were not validated in step 5."

False-positive listesi (tam):

> "Use this list when evaluating issues in Steps 4 and 5 (these are false positives, do NOT flag):
>
> - Pre-existing issues
> - Something that appears to be a bug but is actually correct
> - Pedantic nitpicks that a senior engineer would not flag
> - Issues that a linter will catch (do not run the linter to verify)
> - General code quality concerns (e.g., lack of test coverage, general security issues) unless explicitly required in CLAUDE.md
> - Issues mentioned in CLAUDE.md but explicitly silenced in the code (e.g., via a lint ignore comment)"

Yorum biçimi:

> "- For small, self-contained fixes, include a committable suggestion block
> - For larger fixes (6+ lines, structural changes, or changes spanning multiple locations), describe the issue and suggested fix without a suggestion block
> - Never post a committable suggestion UNLESS committing the suggestion fixes the issue entirely."
> "**IMPORTANT: Only post ONE comment per unique issue. Do not post duplicate comments.**"
> "No issues found. Checked for bugs and CLAUDE.md compliance."

Link biçimi: "Requires full git sha", "Line range format is L[start]-L[end]", "Provide at least 1 line of context before and after".

claude.com/plugins/code-review sayfası ayrıca: "Each finding is scored on a 0-100 confidence scale, only high-confidence issues (default threshold: 80) are posted as comments" — ancak GitHub'daki komut dosyasında sayısal ölçek yok; bu uyumsuzluğu not ediyorum.

Ne yapar: Severity taksonomisi yok, "flag / do not flag" ikili listesi ve doğrulama ajanı var; pre-existing ve lint'in yakalayacağı her şey dışarıda.

### 1.4 OpenAI Codex GitHub code review dokümanı (R) — https://learn.chatgpt.com/docs/third-party/github (developers.openai.com/codex/cloud/code-review buraya yönlendiriyor)

> "Codex reviews the pull request diff, follows your repository guidance, and posts a standard GitHub code review"
> "In GitHub, Codex flags only P0 and P1 issues so review comments stay focused on high-priority risks."
> "Codex searches your repository for `AGENTS.md` files and follows the applicable code review rules."
> "Add a `## Code Review Rules` section to the file closest to the code the rules govern."
> "Codex applies the root and more-specific guidance that covers each changed file."

Resmi örnek kural: "Do not filter treatment comparisons on post-exposure behavior, including conversion or retention."

Yazım ipuçları (dokümanın ifadesi): "consequential, repository-specific behavior", "the safe path or exception", "Leave mechanical checks in CI."

> "Code review rules guide Codex; they don't replace tests, branch protections, or required approvals."

Yorum biçimi: bot yorumu `[P1]` etiketi + başlık + açıklama + kod referansı; örnek başlık "Approving MCP tools never notifies the server." Takip komutları: "@codex review for issues in the database migration", "@codex fix the P1 issue", "@codex security review".

Ne yapar: Kural dosyası AGENTS.md'nin tek bölümü; GitHub'da P2/P3 asla yayınlanmaz; kural metni "flag X; safe path Y" kalıbında.

### 1.5 Codex `/review` sistem prompt'u (`codex-rs/core/review_prompt.md`, gist kopyası) (S) — https://gist.github.com/cbh123/ce4893a10ed2b87a89d9114b08118a08

Tam metin `dl/codex_gist.md` (6.4 KB). Çekirdek bölümler:

Rol ve geçersiz kılma:

> "You are acting as a reviewer for a proposed code change made by another engineer."
> "These are not the final word in determining whether an issue is a bug. In many cases, you will encounter other, more specific guidelines. These may be present elsewhere in a developer message, a user message, a file, or even elsewhere in this system message. Those guidelines should be considered to override these general instructions."

Bug sayılma ölçütleri (sekiz madde, tam):

> "1. It meaningfully impacts the accuracy, performance, security, or maintainability of the code.
> 2. The bug is discrete and actionable (i.e. not a general issue with the codebase or a combination of multiple issues).
> 3. Fixing the bug does not demand a level of rigor that is not present in the rest of the codebase (e.g. one doesn't need very detailed comments and input validation in a repository of one-off scripts in personal projects)
> 4. The bug was introduced in the commit (pre-existing bugs should not be flagged).
> 5. The author of the original PR would likely fix the issue if they were made aware of it.
> 6. The bug does not rely on unstated assumptions about the codebase or author's intent.
> 7. It is not enough to speculate that a change may disrupt another part of the codebase, to be considered a bug, one must identify the other parts of the code that are provably affected.
> 8. The bug is clearly not just an intentional change by the original author."

Yorum kuralları (seçme):

> "2. The comment should appropriately communicate the severity of the issue. It should not claim that an issue is more severe than it actually is.
> 3. The comment should be brief. The body should be at most 1 paragraph.
> 4. The comment should not include any chunks of code longer than 3 lines.
> 5. The comment should clearly and explicitly communicate the scenarios, environments, or inputs that are necessary for the bug to arise. The comment should immediately indicate that the issue's severity depends on these factors.
> 6. The comment's tone should be matter-of-fact and not accusatory or overly positive.
> 8. The comment should avoid excessive flattery and comments that are not helpful to the original author. The comment should avoid phrasing like "Great job ...", "Thanks for ..."."

Hacim kuralı (tam):

> "HOW MANY FINDINGS TO RETURN:
>
> Output all findings that the original author would fix if they knew about it. If there is no finding that a person would definitely love to see and fix, prefer outputting no findings. Do not stop at the first qualifying finding. Continue until you've listed every qualifying finding."

> "- Ignore trivial style unless it obscures meaning or violates documented standards.
> - Use one comment per distinct issue (or a multi-line range if necessary)."
> "Avoid ranges longer than 5–10 lines; instead, choose the most suitable subrange that pinpoints the problem."

Öncelik tanımları (tam):

> "At the beginning of the finding title, tag the bug with priority level. For example "[P1] Un-padding slices along wrong tensor dimensions". [P0] – Drop everything to fix.  Blocking release, operations, or major usage. Only use for universal issues that do not depend on any assumptions about the inputs. · [P1] – Urgent. Should be addressed in the next cycle · [P2] – Normal. To be fixed eventually · [P3] – Low. Nice to have."

Verdict:

> "Correct implies that existing code and tests will not break, and the patch is free of bugs and other blocking issues.
> Ignore non-blocking issues such as style, formatting, typos, documentation, and other nits."

Çıktı şeması (tam):

```json
{
  "findings": [
    {
      "title": "<≤ 80 chars, imperative>",
      "body": "<valid Markdown explaining *why* this is a problem; cite files/lines/functions>",
      "confidence_score": <float 0.0-1.0>,
      "priority": <int 0-3, optional>,
      "code_location": {
        "absolute_file_path": "<file path>",
        "line_range": {"start": <int>, "end": <int>}
      }
    }
  ],
  "overall_correctness": "patch is correct" | "patch is incorrect",
  "overall_explanation": "<1-3 sentence explanation justifying the overall_correctness verdict>",
  "overall_confidence_score": <float 0.0-1.0>
}
```

> "* The code_location should overlap with the diff.
> * Do not generate a PR fix."

Ne yapar: "Yazar bunu düzeltmek ister miydi?" ölçütü, sekiz maddelik bug tanımı, "prefer outputting no findings" + "do not stop at the first", her bulguya confidence ve P0-P3.

### 1.6 OpenAI Cookbook, Codex SDK ile inceleme (R) — https://developers.openai.com/cookbook/examples/codex/build_code_review_with_codex_sdk

> "You are acting as a reviewer for a proposed code change made by another engineer."
> "Focus on issues that impact correctness, performance, security, maintainability, or developer experience."
> "Flag only actionable issues introduced by the pull request."
> "When you flag an issue, provide a short, direct explanation and cite the affected file and line range."
> "Prioritize severe issues and avoid nit-level comments unless they block understanding of the diff."
> "Ensure that file citations and line numbers are exactly correct using the tools available;" (devamı: yanlış alıntı yorumun reddedilmesine yol açar)

Şema 1.5 ile aynı: `title` ≤80, `body`, `confidence_score` 0-1, `priority` 0-3, `code_location`, `overall_correctness` ∈ {"patch is correct","patch is incorrect"}, `overall_confidence_score`.

### 1.7 Cloudflare "Orchestrating AI code review at scale" (B) — https://blog.cloudflare.com/ai-code-review/ (2026-04, Agents Week)

Mimari cümlesi:

> "Instead of asking one model to review everything, we split the review into domain-specific agents. Each agent has a tightly scoped prompt telling it exactly what to look for, and more importantly, what to ignore."

Security reviewer prompt'u (gösterilen tek tam prompt parçası):

```markdown
## What to Flag
- Injection vulnerabilities (SQL, XSS, command, path traversal)
- Authentication/authorisation bypasses in changed code
- Hardcoded secrets, credentials, or API keys
- Insecure cryptographic usage
- Missing input validation on untrusted data at trust boundaries
## What NOT to Flag
- Theoretical risks that require unlikely preconditions
- Defense-in-depth suggestions when primary defenses are adequate
- Issues in unchanged code that this MR doesn't affect
- "Consider using library X" style suggestions
```

> "The security reviewer, for example, has explicit instructions to only flag issues that are "exploitable or concretely dangerous""

> "It turns out that telling an LLM what not to do is where the actual prompt engineering value resides. Without these boundaries, you get a firehose of speculative theoretical warnings that developers will immediately learn to ignore."

Severity:

> "Every reviewer produces findings in a structured XML format with a severity classification: critical (will cause an outage or is exploitable), warning (measurable regression or concrete risk), or suggestion (an improvement worth considering). This ensures we are dealing with structured data that drives downstream behavior, rather than parsing advisory text."

Prompt'un nasıl kurulduğu:

> "Agent prompts are built at runtime by concatenating the agent-specific markdown file with a shared REVIEWER_SHARED.md file containing mandatory rules. The coordinator's input prompt is assembled by stitching together MR metadata, comments, previous review findings, diff paths, and custom instructions into structured XML."

Sınır etiketleri (prompt injection'a karşı sökülenler): `"mr_input", "mr_body", "mr_comments", "mr_details", "changed_files", "existing_inline_findings", "previous_review", "custom_review_instructions", "agents_md_template_instructions"`.

Koordinatör hakem geçişi:

> "Speculative issues, nitpicks, false positives, and convention-contradicted findings get dropped."
> "If the coordinator isn't sure, it uses its tools to read the source code and verify."

Onay rubriği (satırlar): "All LGTM ("looks good to me"), or only trivial suggestions" → approved; "Some warnings, no production risk" → approved_with_comments; "Multiple warnings suggesting a risk pattern" → minor_issues (POST /unapprove); "Any critical item, or production safety risk" → significant_concerns (requested_changes). "The bias is explicitly toward approval, meaning a single warning in an otherwise clean MR still gets approved_with_comments rather than a block." İnsan "break glass" yazarsa zorla onay.

Re-review kuralları (tam):

> "The re-review rules are strict:
> Fixed findings: Omit from the output, and the MCP server auto-resolves the corresponding DiffNote thread.
> Unfixed findings: Must be re-emitted even if unchanged, so the MCP server knows to keep the thread alive.
> User-resolved findings: Respected unless the issue has materially worsened.
> User replies: If a developer replies "won't fix" or "acknowledged", the AI treats the finding as resolved. If they reply "I disagree", the coordinator will read their justification and either resolve the thread or argue back."

Risk katmanları (kod, tam):

```ts
if (fileCount > 50 || hasSecurityFiles) return "full";
if (totalLines <= 10 && fileCount <= 20)  return "trivial";
if (totalLines <= 100 && fileCount <= 20) return "lite";
return "full";
```

> "You don't need seven concurrent AI agents burning Opus-tier tokens to review a one-line typo fix in a README."

Trivial: 2 ajan, koordinatör Opus→Sonnet; Lite: 4 ajan; Full: 7+ ajan. Güvenlik yolları (`auth/`, `crypto/`) her zaman full.

AGENTS.md reviewer materiality:

> "High materiality (strongly recommend update): package manager changes, test framework changes, build tool changes, major directory restructures, new required env vars, CI/CD workflow changes.
> Medium materiality (worth considering): major dependency bumps, new linting rules, API client changes, state management changes.
> Low materiality (no update needed): bug fixes, feature additions using existing patterns, minor dependency updates, CSS changes."
> "It also penalizes anti-patterns in existing AGENTS.md files, like generic filler ("write clean code"), files over 200 lines that cause context bloat, and tool names without runnable commands."

Özelleştirme: "Teams can customise behavior by dropping an AGENTS.md file in their repo root with project-specific review instructions". Prompt boyutu: "when the coordinator's prompt exceeds 50% of the estimated context window, we emit a warning."

Rakamlar (2026-03-10 → 04-09): 131.246 inceleme, 48.095 MR, 5.169 repo; MR başına ortalama 2,7 inceleme; medyan 3 dk 39 sn, P99 10 dk 21 sn; break glass 288 (%0,6); maliyet ort. $1,19 / medyan $0,98 / P99 $4,45; 159.103 bulgu (~1,2/inceleme); security 11.985 bulgu, 484 critical (~%4); cache hit %85,7; zaman aşımı görev başına 5 dk (code quality 10), toplam 25 dk.

Ne yapar: Prompt = alan-özel "flag / NOT flag" + paylaşılan zorunlu kurallar; üç severity, yapısal XML; koordinatör gürültüyü düşürür ve emin değilse kaynağı okur; re-review durum makinesi tanımlı.

### 1.8 Cursor "Building Bugbot" (B) — https://cursor.com/blog/building-bugbot (2026-02)

Erken akış (tam liste):

> "Run eight parallel passes with randomized diff order
> Combine similar bugs into one bucket
> Majority voting to filter out bugs found during only one pass
> Merge each bucket into a single clear description
> Filter out unwanted categories (like compiler warnings or documentation errors)
> Run results through a validator model to catch false positives
> Dedupe against bugs posted from previous runs"

> "Each pass received a different ordering of the diff, which nudged the model toward different lines of reasoning. When several passes independently flagged the same issue, we treated it as a stronger signal that the bug was real."

Prompt dersi (tam):

> "The agentic loop forced us to rethink prompting. With earlier versions of Bugbot we needed to restrain the models to minimize false positives. But with the agentic approach we encountered the opposite problem: it was too cautious. We shifted to aggressive prompts that encouraged the agent to investigate every suspicious pattern and err on the side of flagging potential issues."

Kurallar: "teams also needed a way to encode codebase-specific invariants like unsafe migrations or incorrect use of internal APIs. In response, we added Bugbot rules to support those checks without hardcoding them into the system."

Ölçüm:

> "we devised a metric called the resolution rate. It uses AI to determine, at PR merge time, which bugs were actually resolved by the author in the final code."
> "Since launch, we have run 40 major experiments that have increased Bugbot's resolution rate from 52% to over 70%, while lifting the average number of bugs flagged per run from 0.4 to 0.7. This means that the number of resolved bugs per PR has more than doubled, from roughly 0.2 to about 0.5."
> "Many changes, surprisingly, regressed our metrics."

Ne yapar: Prompt metni yayımlanmadı; ders şu: ajan araç çağırabildiğinde "restrain" yerine "aggressive + investigate"; gürültü prompt'ta değil, oylama/doğrulayıcı/kategori filtresi katmanında kesiliyor.

### 1.9 Cursor Bugbot dokümanı (R) — https://cursor.com/docs/bugbot

> "Create `.cursor/BUGBOT.md` files to provide project-specific context for reviews."
> "Bugbot always includes the root `.cursor/BUGBOT.md` file and any additional files found while traversing upward from changed files."
> "Cursor project rules (`*.mdc` files in `.cursor/rules/`) do not apply to Bugbot runs."

Kural yapısı: Name / Rule content / Scoped paths (glob). Birleştirme sırası: "Team Rules → project .cursor/BUGBOT.md (including nested files) → learned rules → manual rules." Limitler: "Each rule is truncated at 30,000 characters when included in a review." "The combined rules Bugbot includes for a review are capped at 100,000 characters." "Required team rules are prioritized over non-required rules."

Örnek kurallar (yapı: koşul → blocking/non-blocking Bug + başlık + gövde + etiket):

> "If any changed file contains the string pattern /\beval\s*\(|\bexec\s*\(/i, then:" → blocking Bug "Dangerous dynamic execution", label "security"
> "If the PR modifies dependency files (package.json, pnpm-lock.yaml, yarn.lock, requirements.txt, go.mod, Cargo.toml), then:" → License Scan; GPL-2.0/3.0, AGPL-3.0 → blocking Bug "Disallowed license detected"
> "For files matching **/*.{js,jsx,ts,tsx} in React projects:" `/componentWillMount\s*\(/` → blocking Bug "Deprecated React lifecycle method", body "Replace componentWillMount with constructor or useEffect. See React docs."
> "If the PR modifies files in {server/**, api/**, backend/**} and there are no changes in {**/*.test.*, **/__tests__/**, tests/**}, then:" → blocking Bug "Missing tests for backend changes.", body "This PR modifies backend code but includes no accompanying tests. Please add or update tests."
> "If any changed file contains /(?:^|\s)(TODO|FIXME)(?:\s*:|\s+)/, then:" → non-blocking Bug "TODO/FIXME comment found.", body "Replace TODO/FIXME with a tracked issue reference, e.g., `TODO(#1234): ...`, or remove it."

Severity: kural sayfasında yalnızca blocking/non-blocking; API analitiğinde `severity` "high"/"medium"/null.

Ne yapar: Kurallar deterministik "if pattern then Bug" biçiminde; severity iki değerli; kural toplamı 100k karakterle sınırlı.

### 1.10 Greptile (R) — https://www.greptile.com/docs/code-review/greptile-config-reference ve https://www.greptile.com/docs/code-review/custom-standards.md

Kural yazma rehberi (tam):

> "Rules must be specific and measurable:"
> ❌ "Write clean code"  ✅ "Functions must not exceed 50 lines"  ✅ "All API responses must include `status` and `timestamp` fields"
> Bad: "Follow best practices"  Good: "Variable names must be camelCase, min 3 characters, no Hungarian notation"
> "Include examples in your rule for best results:"

Tam config örneği:

```json
"instructions": "This is a TypeScript monorepo using pnpm workspaces. We use Prisma for database access and zod for validation.",
"rules": [
  {
    "id": "no-console",
    "rule": "Do not use console.log in production code. Use the logger service instead.",
    "scope": ["src/**"],
    "severity": "medium"
  },
  {
    "rule": "All async functions must have error handling.",
    "severity": "high"
  }
]
```

Diğer örnek kurallar: "Use parameterized queries. Never interpolate user input into SQL strings." (scope `src/db/**`, severity `high`), "All API endpoints must have rate limiting" (`src/api/**/*.ts`), "All async functions must use try-catch blocks. Never swallow errors silently", "No direct database queries in controllers", "No TODO comments".

Eşik: `strictness` "Comment threshold", varsayılan 2; "`1` = verbose (flags more issues)", "`3` = critical only (flags fewer issues)". `commentTypes` varsayılan `["syntax", "logic", "style"]`. `instructions`: "Free-form instructions for the reviewer. When cascading, instructions from all parent configs are concatenated together." Öncelik: `.greptile/` varsa `greptile.json` yok sayılır; alt dizin config'leri Şubat 2026'dan beri üst ayarları geçersiz kılar.

Ne yapar: Kural = tek cümle + glob + severity; hacim bir sayısal eşikle (1-3) kontrol edilir.

### 1.11 CodeRabbit (R) — https://docs.coderabbit.ai/configuration/path-instructions ve https://docs.coderabbit.ai/reference/configuration

Resmi path_instructions örneği (tam):

```yaml
reviews:
  path_instructions:
    - path: "src/controllers/**"
      instructions: |
        - Focus on authentication, authorization, and input validation.
        - Flag any direct database queries that bypass the ORM layer.
    - path: "tests/**"
      instructions: |
        Review the following unit test code written using the Mocha test library. Ensure that:
        - The code adheres to best practices associated with Mocha.
        - Descriptive test names are used to clearly convey the intent of each test.
        - Edge cases and error paths are covered.
    - path: "docs/**.md"
      instructions: |
        Check for clarity, accuracy, and completeness.
        Flag any references to deprecated APIs or outdated behavior.
```

> "Path instructions work best as a targeted supplement, not a replacement. Observe a few reviews first."
> "They do not disable other features that inspect the same code."

Hacim profili `reviews.profile` (varsayılan chill): "quiet for only the most important feedback, chill for balanced feedback, assertive for more feedback"; `quiet`: "Posts only the most important comments inline and groups the other review comments in the review summary."; `assertive`: "More feedback, which may feel nitpicky." `instructions` alanı maks. 20.000 karakter; `tone_instructions` maks. 250 ("You must talk like Mr. T. I pity the fool who doesn't!"). `@coderabbitai emit path instructions` son 7 günün önerilerini config PR'ına toplar.

Ne yapar: Severity taksonomisi yok; hacim üç profil ile; kurallar path-glob'a bağlı serbest metin.

### 1.12 cubic (R) — https://docs.cubic.dev/ai-review/custom-context.md

Dashboard alanı: "plaintext instructions that will be included in every review". Tek seferlik: "@cubic-dev-ai rerun and focus on auth edge cases". Otomatik okunan context dosyaları: README.md, AGENTS.md, CLAUDE.md, .cursorrules, copilot-instructions.md, .coderabbit.yaml, `.claude/skills/`, `.codex/skills/`, `.ai/`, `.cursor/rules/` vb. Rehber: "Be specific and actionable." ("write good code" yerine "use React hooks instead of class components"); "Context files provide background information, while custom agents actively flag violations." Custom rules Aralık 2025'te "Custom Agents" oldu; örnek kural "No console logs in production." CLI: `cubic review --prompt "check for XSS vulnerabilities"`.

### 1.13 GitHub Copilot code review (R) — https://docs.github.com/en/copilot/tutorials/customize-code-review ve https://docs.github.com/en/copilot/how-tos/use-copilot-agents/request-a-code-review/use-code-review

Resmi `.github/copilot-instructions.md` örneği (tam):

```markdown
# General Code Review Standards

## Purpose
These instructions guide Copilot code review across all files in this repository.
Language-specific rules are in separate instruction files.

## Security Critical Issues
- Check for hardcoded secrets, API keys, or credentials
- Look for SQL injection and XSS vulnerabilities
- Verify proper input validation and sanitization
- Review authentication and authorization logic

## Performance Red Flags
- Identify N+1 database query problems
- Spot inefficient loops and algorithmic issues
- Check for memory leaks and resource cleanup
- Review caching opportunities for expensive operations

## Code Quality Essentials
- Functions should be focused and appropriately sized (under 50 lines)
- Use clear, descriptive naming conventions
- Ensure proper error handling throughout
- Remove dead code and unused imports

## Review Style
- Be specific and actionable in feedback
- Explain the "why" behind recommendations
- Acknowledge good patterns when you see them
- Ask clarifying questions when code intent is unclear

## Testing Standards
- New features require unit tests
- Tests should cover edge cases and error conditions
- Test names should clearly describe what they test

Always prioritize security vulnerabilities and performance issues that could impact users.
```

Uzunluk: "Begin with 10–20 specific instructions that address your most common review needs, then test whether these are influencing Copilot code review in the way you intended." "Very long instruction files may result in some instructions being overlooked." "Limit any single instruction file to a maximum of about 1,000 lines." Ve use-code-review sayfası: "Copilot code review only reads the first 4,000 characters of any custom instruction file. Any instructions beyond this limit will not affect the reviews generated by Copilot code review."

Desteklenmeyen talimat türleri (tam liste): "Use bold text for critical issues", "Change the format of review comments", "Add emoji to comments", "Include a summary of security issues in the PR overview", "Block a PR from merging unless all Copilot code review comments are addressed", "Review this code according to the standards at https://example.com/standards", "Be more accurate", "Don't miss any issues", "Be consistent in your feedback".

Dosya yerleri: `.github/copilot-instructions.md`, kökte `AGENTS.md`, `.github/instructions/**/*.instructions.md` (frontmatter `applyTo: "**/*.py"`); "Copilot code review also reads custom instructions from `CLAUDE.md`, `GEMINI.md`, and `REVIEW.md` files". Severity: "Copilot labels each comment with a severity level of "High," "Medium," or "Low"". Lite effort: "provides targeted feedback on glaring issues such as bugs, security vulnerabilities, and style inconsistencies."

Ne yapar: 4.000 karakter sert sınır; "Don't miss any issues" gibi belirsiz talimatlar resmen "desteklenmiyor".

### 1.14 Devin Review (R) — https://docs.devin.ai/work-with-devin/devin-review

Resmi örnek REVIEW.md (tam):

```markdown
# Review Guidelines

## Critical Areas
- All changes to `src/auth/` must be reviewed for security implications.
- Database migration files should be checked for backward compatibility.

## Conventions
- API endpoints must include input validation and proper error handling.
- All public functions require TypeScript return types — do not use `any`.
- React components should use functional components with hooks, not class components.

## Ignore
- Auto-generated files in `src/generated/` do not need review.
- Lock files (package-lock.json, yarn.lock) can be skipped unless dependencies changed.

## Performance
- Flag any database queries inside loops.
- Watch for N+1 query patterns in API resolvers.
```

Sınıflar: "Bugs are actionable errors that should be fixed in the code. These represent issues the Bug Catcher has high confidence are actual problems." Severe: "High-confidence issues that require immediate attention"; Non-severe: "Lower severity issues that should still be reviewed". "Flags are informational code annotations that may or may not require action." Investigate: "Flags that warrant further investigation. You should review the flagged code yourself and verify whether there is an actual bug or issue."; Informational: "The Bug Catcher has either concluded correctness or is explaining how something works." Security Critical: "High-confidence vulnerabilities that should be fixed before merging"; Warning: "Potential security weaknesses worth investigating". Investigate/Informational flag'ler varsayılan olarak PR yorumu olarak yayınlanmaz. Dosyalar: `**/REVIEW.md`, `**/AGENTS.md`.

### 1.15 obra/superpowers `code-reviewer.md` (S) — https://github.com/obra/superpowers/blob/main/skills/requesting-code-review/code-reviewer.md

Tam metin `dl/superpowers_reviewer.md` (6.4 KB). Öne çıkanlar:

> "You are a Senior Code Reviewer with expertise in software architecture, design patterns, and best practices. Your job is to review completed work against its plan or requirements and identify issues before they cascade."

Spec yorumu:

> "The spec says what the software must do. It does not enumerate every input, environment, or condition the software will meet. For behavior the spec is silent on, judge by what a reasonable person using this software would expect: a reasonable person's expectation is a requirement, and a spec's silence is not permission."

"Declined to judge" listesi:

> "Before your verdict, list every behavior you considered and set aside as outside the plan or spec, one line each, with the reason. The executor rules on each line; nothing you set aside is dropped silently."

Alt-ajan yasağı: "Do all of this review yourself. Never spawn a subagent to review part of the diff, and never spawn another reviewer for a second opinion. This process already provides every review seat the work gets".

Kalibrasyon: "Categorize issues by actual severity. Not everything is Critical. Acknowledge what was done well before listing issues — accurate praise helps the implementer trust the rest of the feedback."

Çıktı: `### Strengths` / `### Issues` → `#### Critical (Must Fix)` "[Bugs, security issues, data loss risks, broken functionality]", `#### Important (Should Fix)` "[Architecture problems, missing features, poor error handling, test gaps]", `#### Minor (Nice to Have)` "[Code style, optimization opportunities, documentation polish]"; her issue için "File:line reference / What's wrong / Why it matters / How to fix (if not obvious)"; `**Ready to merge?** [Yes | No | With fixes]`.

DON'T listesi: "Say "looks good" without checking / Mark nitpicks as Critical / Give feedback on code you didn't actually read / Be vague ("improve error handling") / Avoid giving a clear verdict".

### 1.16 affaan-m/everything-claude-code `agents/code-reviewer.md` (S) — https://github.com/affaan-m/everything-claude-code/blob/main/agents/code-reviewer.md

Tam metin `dl/ecc_reviewer.md` (13.9 KB). Çekirdek:

> "Only report issues you are confident about (>80% sure it is a real problem)."
> "- **Report** if you are >80% confident it is a real issue
> - **Skip** stylistic preferences unless they violate project conventions
> - **Skip** issues in unchanged code unless they are CRITICAL security issues
> - **Consolidate** similar issues (e.g., "5 functions missing error handling" not 5 separate findings)"

Pre-Report Gate (tam):

> "1. **Can I cite the exact line?** Name the file and line. Vague findings like "somewhere in the auth layer" are not actionable and must be dropped.
> 2. **Can I describe the concrete failure mode?** Name the input, state, and bad outcome. If you cannot name the trigger, you are pattern-matching, not reviewing.
> 3. **Have I read the surrounding context?** Check callers, imports, and tests. Many apparent issues are already handled one frame up or guarded by a type.
> 4. **Is the severity defensible?** A missing JSDoc is never HIGH. A single `any` in a test fixture is never CRITICAL. Severity inflation erodes trust faster than missed findings."

> "For any finding tagged HIGH or CRITICAL, include:
> - The exact snippet and line number
> - The specific failure scenario: input, state, and outcome
> - Why existing guards, such as types, validation, or framework defaults, do not catch it
>
> If you cannot produce all three, demote to MEDIUM or drop."

Sıfır bulgu:

> "A clean review is a valid review. Do not manufacture findings to justify the invocation. [...] Manufactured findings, filler nits, speculative "consider using X", and hypothetical edge cases without a trigger are the primary failure mode of LLM reviewers and directly undermine this agent's usefulness."

Sık false-positive listesi: "Consider adding error handling", "Missing input validation", "Magic number", "Function too long", "Missing JSDoc", "Prefer `const` over `let`", "Possible null dereference", "N+1 query", "Missing await", "Should use TypeScript", "Hardcoded value", "Security theater" — her biri ne zaman gerçek değil açıklamasıyla; kapanış: "Would a senior engineer on this team actually change this in review?" If no, skip."

Verdict: "**Approve**: No CRITICAL or HIGH issues, including clean reviews with zero findings. This is a valid and expected outcome." / "**Warning**: HIGH issues only (can merge with caution)" / "**Block**: CRITICAL issues found — must fix before merge" / "Do not withhold approval to appear rigorous. If the diff is clean, approve it."

### 1.17 Topluluk Codex AGENTS.md örnekleri (S)

agentpedia.codes — https://agentpedia.codes/blog/codex-code-review-agents-md-rules — kök AGENTS.md:

```markdown
## Code Review Rules
### Public API compatibility
- Flag removal or renaming of a public HTTP response field that may be used by
  a released client. Explain which route and field changed.
  Safe path: preserve the existing field during the documented deprecation
  window, or add a backward-compatible alias with a migration note.
### Sensitive data in logs
- Flag new logs that can include access tokens, session cookies, payment
  details, or unredacted request bodies.
  Safe path: log the stable request ID and an approved non-sensitive status;
  redact any allowlisted diagnostic field before it reaches the logger.
### Destructive data changes
- Flag a migration that drops or renames stored data before all deployed
  readers have stopped using it.
  Safe path: use expand–migrate–contract and remove the old shape in a later,
  separately reviewed release.
```

İç içe `services/payments/AGENTS.md`:

```markdown
## Code Review Rules
### Money movement state
- Flag code that marks a payment, refund, or payout successful before the
  provider result is durably recorded and reconciled.
  Safe path: persist the provider reference and terminal state atomically, or
  leave the operation pending for the reconciliation worker.
### Retry safety
- Flag a retryable money-movement request that lacks a stable idempotency key.
  Safe path: derive the key from the durable operation ID and reuse it for
  every attempt of the same operation.
```

open-agent-security/openaca PR #210 — https://github.com/open-agent-security/openaca/pull/210 — gözlem: "Our ## Code Review Rules listed P0 through P3 and called P2 "eligible for automatic fixing". Codex read that as permission to post P2s." PR kuralları P0/P1'e daraltıyor; resmi cümleyi alıntılıyor: "In GitHub, Codex flags only P0 and P1 issues so review comments stay focused on high-priority risks."

melodic-software/standards PR #668 — https://github.com/melodic-software/standards/pull/668 — "a convention for the pointer-only `## Code Review Rules` section": her repo AGENTS.md'sinde başlık + intro satırı + tek bir `REVIEW.md` işaretçisi; kontrol "requires the heading once, the intro line verbatim inside the section". Kardeş PR #5967 Codex'in işaretçideki dosyayı açıp açmadığını sınıyor: "The Codex docs do not say."

DataCamp — https://www.datacamp.com/tutorial/claude-code-review — REVIEW.md:

```markdown
# Review instructions
## Important findings
Report as Important:
- Incorrect joins or filters that can change dataset grain
- Missing tenant or customer scoping
- Secrets or credentials written to logs
- Silent changes to revenue or customer metrics
## Do not report
- Formatting already enforced by Ruff
- Generated files
- *.lock files
## Always check
- New transformations have tests
- Joins use the intended keys
- Datetime operations specify timezone assumptions
- Missing values are handled explicitly
```

Yerel `/code-review` çıktı örneği: "🔴 Important / weekly_revenue.py:9 / The merge on customer_id can duplicate order rows because customers contains multiple records per customer. [...] Verify that customer_id is unique in customers or join against the intended current-record subset before aggregating revenue."

### 1.18 Qiu & Gill, "Adversarial Review: Structured Disagreement for Grounded Agentic Code Review", arXiv 2608.18167 (P) — https://arxiv.org/abs/2608.18167 (2026-08-16, ICML 2026 DL4C workshop)

Reviewer prompt'ları:

> LCB reviewer: "Flag bugs, edge cases, and logic errors ONLY." + "Do not comment on style." Verdict: "APPROVE" veya "NEEDS_CHANGES: <one-line summary of top issue>".
> SWE-PRBench reviewer: "Identify bugs, logic errors, and missing edge-case handling IN THIS DIFF." + "cite file:line or code snippets."

Critic (baseline): her flag "actually a real bug" mu ve reviewer "missed any real bugs" mı; "AGREE" / "DISAGREE: <summary>".

Üç-verdict kısıtı (AR with text constraint, A.2.4):

> AGREE: "Use when every flag is real and you have nothing to add."
> DISAGREE_EVIDENCE: "Use when you can ground your objection in code visible in the diff."
> DISAGREE_CONCERN: "Use when your objection is epistemic (reviewer hedged, you have a gut reaction, external attribution argument) but you cannot point to code that refutes the flag. The reviewer's job on the next round is then to firm up the flag with evidence or drop it."
> "Do NOT use DISAGREE_CONCERN as a dismissal mechanism -- use it to request evidence, not to suppress findings."

Reviewer yanıt kuralları (A.2.3):

> AGREE: "The critic accepts your review. Keep ALL your flags unchanged." "Do NOT consolidate, drop, or rephrase legitimate findings just because you are about to converge -- preserve them as-is."
> DISAGREE_CONCERN: "Do NOT capitulate to APPROVE merely because the critic called the concern "speculative"" — ya bug'ı doğrulayan diff kodunu ya da çürüten kodu göster.

MARS meta-reviewer: "Do NOT count votes", "Confidence scores are signals, not deciders", reviewer "can be confidently wrong". Reviewer alanları: Decision, "Confidence: [1-5] (self-reported; 5 = certain)", Justification, Errors.

SKILL.md ilkesi: "Core principle: Self-review is not review. A single reviewer is not enough. Adversarial validation catches what consensus misses."

Sonuçlar: SWE-PRBench F1 — AR+text constraint 0.533, Two-reviewers 0.503, MARS 0.501, Single-reviewer 0.495, AR (kısıtsız) 0.457. LiveCodeBench pass: Zero-shot %77, Single-reviewer %77, Two-reviewers %75, MARS %82, AR %87. SWE-bench Verified (N=500): AR %75,2, MARS %72,6, Zero-shot %71,6; AR token maliyeti Zero-shot'ın ~4,5 katı.

Ne yapar: Tek prompt değişikliği (critic'e "kanıt göster ya da endişe olarak işaretle" üçlü verdict) F1'i 0.457→0.533 taşıyor; ikinci reviewer eklemek (Two-reviewers) tek reviewer'dan ayırt edilemiyor.

### 1.19 Jin & Chen, "Are LLMs Reliable Code Reviewers? Systematic Overcorrection in Requirement Conformance Judgement", arXiv 2603.00539 (P) — https://arxiv.org/abs/2603.00539 (2026-03)

Özet: "we demonstrate that LLMs frequently misclassify correct code implementation as non-compliant or defective." "more detailed prompt design, particularly with those requiring explanations and proposed corrections" "leads to higher misjudgment rates."

Ne yapar: Açıklama + düzeltme önerisi istemek yanlış-ret oranını yükseltiyor; "daha ayrıntılı prompt = daha iyi" varsayımına ölçülü karşı kanıt.

### 1.20 SWR-Bench, arXiv 2509.01494 (P) — https://arxiv.org/abs/2509.01494 (2025-09)

"a new benchmark comprising 1000 manually verified Pull Requests (PRs) from GitHub"; "an objective LLM-based evaluation method that aligns strongly with human judgment (~90 agreement)"; "a simple multi-review aggregation strategy" ile "increasing F1 scores by up to 43.67%". v2 tavsiyesi: geri bildirimi severity'ye göre ayırın; çoğu false positive eksik proje bağlamından.

---

## 2. Temalara göre karşılaştırma

### (a) Severity taksonomisi ve tanımlar

| Kaynak | Seviyeler | Tanım metni |
|--------|-----------|-------------|
| Anthropic hosted | Important / Nit / Pre-existing | "A bug that should be fixed before merging" / "A minor issue, worth fixing but not blocking" / "exists in the codebase but was not introduced by this PR" |
| Anthropic plugin | yok (ikili: flag / do not flag) | "HIGH SIGNAL issues" |
| Codex `/review` | P0-P3 | "[P0] – Drop everything to fix. Blocking release, operations, or major usage. Only use for universal issues that do not depend on any assumptions about the inputs. · [P1] – Urgent. Should be addressed in the next cycle · [P2] – Normal. To be fixed eventually · [P3] – Low. Nice to have." GitHub'da yalnız P0/P1 yayınlanır |
| Cloudflare | critical / warning / suggestion | "(will cause an outage or is exploitable)" / "(measurable regression or concrete risk)" / "(an improvement worth considering)" |
| Cursor Bugbot | blocking / non-blocking (kural), high/medium (API) | tanım yok |
| Greptile | kural `severity` high/medium + strictness 1-3 | "1 = verbose", "3 = critical only" |
| CodeRabbit | yok; profil quiet/chill/assertive | "quiet for only the most important feedback" |
| Copilot | High / Medium / Low | tanım verilmemiş |
| Devin | Severe / Non-severe; Investigate / Informational; Critical / Warning | "High-confidence issues that require immediate attention" vb. |
| superpowers | Critical / Important / Minor | "[Bugs, security issues, data loss risks, broken functionality]" / "[Architecture problems, missing features, poor error handling, test gaps]" / "[Code style, optimization opportunities, documentation polish]" |
| ECC | CRITICAL / HIGH / MEDIUM / LOW + Approve/Warning/Block | "A missing JSDoc is never HIGH. A single `any` in a test fixture is never CRITICAL." |

Ortak nokta: en üst seviye hep "merge'i engeller / üretimi bozar / istismar edilebilir"; en az iki satıcı (Codex GitHub, Cloudflare rubriği) tek tek warning'i engelleyici saymaz. Anthropic REVIEW.md rehberi severity'yi repo başına yeniden tanımlamayı açıkça teşvik eder.

### (b) Neyi işaretleme (what NOT to flag)

En net listeler:

- Cloudflare: "Theoretical risks that require unlikely preconditions / Defense-in-depth suggestions when primary defenses are adequate / Issues in unchanged code that this MR doesn't affect / "Consider using library X" style suggestions" + "telling an LLM what not to do is where the actual prompt engineering value resides."
- Anthropic plugin: "Pre-existing issues / Something that appears to be a bug but is actually correct / Pedantic nitpicks that a senior engineer would not flag / Issues that a linter will catch / General code quality concerns [...] unless explicitly required in CLAUDE.md / Issues mentioned in CLAUDE.md but explicitly silenced in the code"; ayrıca "Potential issues that depend on specific inputs or state".
- Codex: "pre-existing bugs should not be flagged"; "Ignore trivial style unless it obscures meaning or violates documented standards"; spekülatif yan etki yasak ("one must identify the other parts of the code that are provably affected"); "clearly not just an intentional change by the original author".
- Anthropic REVIEW.md: "Anything CI already enforces: lint, formatting, type errors / Generated files [...] / Test-only code that intentionally violates production rules".
- ECC: 12 maddelik "Common False Positives - Skip These".
- Cookbook: "avoid nit-level comments unless they block understanding of the diff".
- Best practices: "Report gaps, not style preferences."

### (c) Hacim sınırları

- Anthropic REVIEW.md: "Report at most five Nits per review. If you found more, say "plus N similar items" in the summary"; `/code-review --max-findings <n>|all|default`.
- Codex: üst sınır yok ama alt eşik var: "prefer outputting no findings" + "Do not stop at the first qualifying finding".
- Cursor (blog): ortalama bulgu/çalıştırma 0,4→0,7; sekiz geçiş + çoğunluk oyu; sonra "aggressive" prompt.
- Cloudflare: ölçülen ~1,2 bulgu/inceleme; koordinatör "nitpicks" düşürür.
- Greptile strictness 1-3; CodeRabbit quiet/chill/assertive.
- ECC: "Consolidate similar issues"; "A clean review is a valid review."
- Anthropic plugin: "Only post ONE comment per unique issue."

### (d) Kanıt / doğrulama şartı

- Anthropic REVIEW.md: "behavior claims need a `file:line` citation in the source, not an inference from naming".
- Anthropic plugin: ayrı doğrulama alt-ajanı; "Do not flag issues that you cannot validate without looking at context outside of the git diff"; "If you are not certain an issue is real, do not flag it."
- Anthropic hosted: "a verification step checks candidates against actual code behavior"; her bulguda "Why this was flagged" bölümü.
- Codex: madde 7 "provably affected"; madde 5 "The comment should clearly and explicitly communicate the scenarios, environments, or inputs that are necessary for the bug to arise"; her bulguda `confidence_score`.
- Cookbook: "Ensure that file citations and line numbers are exactly correct using the tools available"; yanlış alıntı reddedilir.
- Cloudflare: "If the coordinator isn't sure, it uses its tools to read the source code and verify."
- Cursor: "validator model to catch false positives"; çoğunluk oyu.
- ECC: Pre-Report Gate 4 soru; HIGH/CRITICAL için "exact snippet and line number / specific failure scenario: input, state, and outcome / Why existing guards [...] do not catch it"; "If you cannot produce all three, demote to MEDIUM or drop."
- AR makalesi: critic yalnızca "code visible in the diff" ile DISAGREE_EVIDENCE verebilir; reviewer "Do NOT capitulate to APPROVE merely because the critic called the concern "speculative"".
- Copilot: "Don't miss any issues" / "Be more accurate" türü talimatlar **desteklenmiyor** — kanıt şartı yerine somut kurallar.

### (e) Re-review / yakınsama

- Anthropic REVIEW.md: "after the first review, suppress new nits and post Important findings only" — "stops a one-line fix from reaching round seven on style alone."
- Anthropic hosted: push'ta yeniden inceleme; "the next run resolves the thread when the issue is fixed"; thread'i kapatmak bulguyu reddeder, yanıt vermek etmez.
- Cloudflare: Fixed → omit + auto-resolve; Unfixed → "Must be re-emitted even if unchanged"; User-resolved → "Respected unless the issue has materially worsened"; "won't fix"/"acknowledged" → resolved; "I disagree" → koordinatör okur, ya kapatır ya "argue back". Ortalama 2,7 inceleme/MR.
- Cursor: "Dedupe against bugs posted from previous runs".
- Anthropic plugin: Claude zaten yorum yaptıysa inceleme yok ("Claude has already commented on this PR" → stop).
- AR makalesi: AGREE'de "Keep ALL your flags unchanged [...] Do NOT consolidate, drop, or rephrase legitimate findings just because you are about to converge".

### (f) Kapsam (diff vs repo, pre-existing)

- Codex: "The bug was introduced in the commit (pre-existing bugs should not be flagged)"; "The code_location should overlap with the diff".
- Anthropic hosted: pre-existing ayrı 🟣 seviye olarak yayınlanır (bastırılmaz, etiketlenir).
- Anthropic plugin: Agent 3 "Focus only on the diff itself without reading extra context"; Agent 4 "Only look for issues that fall within the changed code".
- Cloudflare: "Issues in unchanged code that this MR doesn't affect" → işaretleme; koordinatör ise kaynağı okuyabilir.
- ECC: "Skip issues in unchanged code unless they are CRITICAL security issues"; ama "Read the full file and understand imports, dependencies, and call sites".
- Cursor blog: ajan "call tools, and decide where to dig deeper" — bağlamı kendisi çeker.
- AR: "IN THIS DIFF".

### (g) Çıktı biçimi

- Codex / Cookbook: katı JSON (findings[title≤80, body, confidence_score, priority 0-3, code_location{absolute_file_path, line_range}], overall_correctness, overall_explanation, overall_confidence_score); "Do not wrap the JSON in markdown fences"; başlık "[P1] ..." etiketli; yorum ≤1 paragraf, kod ≤3 satır, aralık ≤5-10 satır.
- Cloudflare: "structured XML format with a severity classification".
- Anthropic hosted: inline yorum + check-run tablosu (Severity | File:Line | Issue) + makine okunur son satır `bughunter-severity: {"normal":2,"nit":1,"pre_existing":0}`; "collapsed Why this was flagged".
- Anthropic plugin: inline, tek yorum/konu, committable suggestion yalnızca tamamen düzeltiyorsa; tam SHA linki, L[start]-L[end], ±1 satır bağlam.
- superpowers: Strengths / Issues (Critical, Important, Minor; her biri File:line, What's wrong, Why it matters, How to fix) / Recommendations / "Ready to merge? [Yes | No | With fixes]".
- ECC: severity gruplu liste + özet tablo + APPROVE/WARNING/BLOCK.
- DataCamp'in gösterdiği `/code-review` çıktısı: "🔴 Important / file:line / açıklama / doğrulama önerisi".
- Copilot: biçim talimatları ("Use bold text", "Add emoji") desteklenmiyor.

### (h) Dosya uzunluğu ve kuralların yaşadığı yer

| Kaynak | Dosya(lar) | Uzunluk kuralı |
|--------|-----------|----------------|
| Anthropic | `REVIEW.md` (kök; review-only) + `CLAUDE.md` (her seviyede, ihlal = nit) | "a long `REVIEW.md` dilutes the rules that matter most"; örnek şablon ~110 kelime; CLAUDE.md için "Would removing this cause Claude to make mistakes?" |
| Anthropic plugin komutu | tek `commands/code-review.md` | ~7,3 KB (~1.100 kelime) |
| Codex | `AGENTS.md` içinde `## Code Review Rules`, en yakın dosya öncelikli | "Leave mechanical checks in CI"; sistem prompt'u ~6,4 KB (~950 kelime) |
| Cloudflare | ajan başına markdown + paylaşılan `REVIEWER_SHARED.md`; repo `AGENTS.md` | AGENTS.md için "files over 200 lines that cause context bloat" cezalandırılır; koordinatör prompt'u bağlamın %50'sini aşarsa uyarı |
| Cursor | `.cursor/BUGBOT.md` (iç içe) + dashboard kuralları | kural ≤30.000 karakter, toplam ≤100.000 |
| Greptile | `greptile.json` / `.greptile/config.json` (cascading) | kural = tek cümle + glob + severity |
| CodeRabbit | `.coderabbit.yaml` `reviews.path_instructions` | instructions ≤20.000 karakter; tone ≤250 |
| Copilot | `.github/copilot-instructions.md`, `.github/instructions/*.instructions.md` (`applyTo`), `AGENTS.md`, `CLAUDE.md`, `REVIEW.md` | **4.000 karakter** (yalnız code review); "10–20 specific instructions"; ≤~1.000 satır |
| Devin | `**/REVIEW.md`, `**/AGENTS.md` | örnek ~90 kelime |
| cubic | `cubic.yaml` + dashboard + tüm context dosyaları | "Be specific and actionable." |
| superpowers | tek şablon dosyası | ~900 kelime |
| ECC | tek agent dosyası | ~2.000 kelime |
| melodic-software | AGENTS.md'de yalnız işaretçi → `REVIEW.md` | "pointer-only" |

---

## 3. En güçlü bulgular (özet)

1. Satıcı prompt'larının ağırlık merkezi "neyi işaretleme" listesidir; Cloudflare bunu açıkça "where the actual prompt engineering value resides" diye yazıyor, Anthropic plugin ve Codex de aynı yapıda.
2. Pre-existing hatalar her yerde ya yasak (Codex, plugin, Cloudflare, ECC) ya ayrı etiketli (Anthropic hosted 🟣).
3. Kanıt şartı ortak: file:line atıfı + somut tetikleyici senaryo; Codex "provably affected", ECC "input, state, and outcome", Anthropic "not an inference from naming".
4. Engelleme eşiği her yerde tek üst seviye: Codex GitHub P0/P1, Cloudflare critical, Anthropic Important, ECC CRITICAL; warning tek başına blok değil ("The bias is explicitly toward approval").
5. Hacim: Anthropic 5 nit kapağı + "plus N similar items"; Codex "prefer outputting no findings" ama "do not stop at the first"; Cursor çoğunluk oyu + doğrulayıcı.
6. Re-review yakınsama: Anthropic "suppress new nits after the first review"; Cloudflare "won't fix"/"acknowledged" = resolved, unfixed yeniden yayınlanır.
7. Prompt uzunluğu: Copilot 4.000 karakter sert sınır; Anthropic "long REVIEW.md dilutes"; Cloudflare 200 satır üstü AGENTS.md'yi cezalandırır; örnek REVIEW.md dosyaları 90-110 kelime.
8. Ölçülü karşı-sezgi: Cursor ajan mimarisine geçince prompt'u "restrain" yerine "aggressive" yaptı; gürültüyü prompt değil doğrulayıcı/oylama kesiyor. Resolution rate %52→%70+.
9. Makale kanıtı: AR'de critic'e "kanıt göster ya da endişe de" üçlü verdict F1 0.457→0.533; ikinci bağımsız reviewer eklemek (0.503) tek reviewer'dan (0.495) ayırt edilemez. Jin & Chen: açıklama/düzeltme isteyen daha ayrıntılı prompt yanlış-ret oranını yükseltir.
10. Copilot resmen "Be more accurate", "Don't miss any issues", "Be consistent" gibi talimatları desteklenmeyen sınıfa koyuyor; somut kural + "safe path" kalıbı (Codex) standart yazım biçimi.

---

## 4. Kaynak listesi

1. R — Anthropic, Claude Code "Code Review" — https://code.claude.com/docs/en/code-review (erişim 2026-10-13)
2. R — Anthropic, Claude Code "Best practices for Claude Code" — https://code.claude.com/docs/en/best-practices (erişim 2026-10-13)
3. R — Anthropic, `plugins/code-review/commands/code-review.md` — https://github.com/anthropics/claude-code/blob/main/plugins/code-review/commands/code-review.md (erişim 2026-10-13); plugin sayfası https://claude.com/plugins/code-review
4. R — OpenAI Codex, "Review GitHub pull requests with Codex" — https://learn.chatgpt.com/docs/third-party/github (developers.openai.com/codex/cloud/code-review yönlendirmesi; erişim 2026-10-13)
5. S — cbh123 gist, "OpenAI Codex PR review agent system prompt (from codex-rs/core/review_prompt.md)" — https://gist.github.com/cbh123/ce4893a10ed2b87a89d9114b08118a08 (2025; ana dalda dosya artık 404)
6. R — OpenAI Cookbook, "Build Code Review with the Codex SDK" — https://developers.openai.com/cookbook/examples/codex/build_code_review_with_codex_sdk (erişim 2026-10-13)
7. B — Cloudflare, Ryan Skidmore, "Orchestrating AI code review at scale" — https://blog.cloudflare.com/ai-code-review/ (2026-04)
8. B — Cursor, "Building Bugbot" — https://cursor.com/blog/building-bugbot (2026-02)
9. R — Cursor, Bugbot docs — https://cursor.com/docs/bugbot (erişim 2026-10-13)
10. R — Greptile, config reference — https://www.greptile.com/docs/code-review/greptile-config-reference ve custom standards https://www.greptile.com/docs/code-review/custom-standards.md (erişim 2026-10-13)
11. R — CodeRabbit, path instructions — https://docs.coderabbit.ai/configuration/path-instructions ve configuration reference https://docs.coderabbit.ai/reference/configuration (erişim 2026-10-13)
12. R — cubic, custom context — https://docs.cubic.dev/ai-review/custom-context.md (erişim 2026-10-13)
13. R — GitHub Docs, "Customize code review" — https://docs.github.com/en/copilot/tutorials/customize-code-review ; "Using GitHub Copilot code review" — https://docs.github.com/en/copilot/how-tos/use-copilot-agents/request-a-code-review/use-code-review ; changelog 2025-06-13 https://github.blog/changelog/2025-06-13-copilot-code-review-customization-for-all/ ; 2025-09-03 https://github.blog/changelog/2025-09-03-copilot-code-review-path-scoped-custom-instruction-file-support
14. R — Devin Docs, "Devin Review" — https://docs.devin.ai/work-with-devin/devin-review (erişim 2026-10-13)
15. S — obra/superpowers, `skills/requesting-code-review/code-reviewer.md` — https://github.com/obra/superpowers/blob/main/skills/requesting-code-review/code-reviewer.md
16. S — affaan-m/everything-claude-code, `agents/code-reviewer.md` — https://github.com/affaan-m/everything-claude-code/blob/main/agents/code-reviewer.md
17. S — agentpedia.codes, "Codex Code Review Rules: AGENTS.md Setup Guide" — https://agentpedia.codes/blog/codex-code-review-agents-md-rules
18. S — open-agent-security/openaca PR #210 "Limit Codex review to P0 and P1 findings" — https://github.com/open-agent-security/openaca/pull/210
19. S — melodic-software/standards PR #668 — https://github.com/melodic-software/standards/pull/668 ; melodic-software/claude-code-plugins PR #5967 — https://github.com/melodic-software/claude-code-plugins/pull/5967
20. S — DataCamp, "Claude Code Review: Catch Bugs Locally and on GitHub" — https://www.datacamp.com/tutorial/claude-code-review
21. P — Qiu, Gill, "Adversarial Review: Structured Disagreement for Grounded Agentic Code Review", arXiv:2608.18167 — https://arxiv.org/abs/2608.18167 (2026-08-16)
22. P — Jin, Chen, "Are LLMs Reliable Code Reviewers? Systematic Overcorrection in Requirement Conformance Judgement", arXiv:2603.00539 — https://arxiv.org/abs/2603.00539 (2026-03)
23. P — "SWR-Bench: Assessing LLM Performance in Real-World Code Review Comment Generation", arXiv:2509.01494 — https://arxiv.org/abs/2509.01494 (2025-09)
24. S — openai/codex issue #9210 "`/review` seems to be extremely verbose" — https://github.com/openai/codex/issues/9210 (kullanıcı, prompt'u Custom instructions'a yapıştırınca P0 etiketlerinin geri geldiğini bildiriyor)
