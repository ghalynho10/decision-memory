# What is decision-memory?

A short explanation. Written in Simplified Technical English.

## The problem

Code shows you what a program does. Code does not show you why.

Months later, you do not know why the team made a decision. The reasons are in old planning documents, commit messages, and conversations. Most of these reasons get lost.

## What the tool does

The tool reads the decision documents in your project. It builds a search index from these documents. Then you ask a question, and the tool gives an answer.

Each answer has a citation. The citation shows the exact file and the exact section that the answer comes from. You can check the answer yourself.

If the documents do not answer your question, the tool tells you. It gives this message: `not enough evidence here`. The tool does not guess.

The tool runs on your computer. Only the search index calls an external service.

## How to use it

Three commands:

| Command | What it does |
|---|---|
| `adapt` | Reads your documents. Makes one record for each decision. |
| `ingest` | Builds the search index. This command calls OpenAI. |
| `query` | Asks a question. Gives an answer with citations. |

You do `adapt` and `ingest` one time. Then you do `query` as many times as you want.

## Example

```console
$ decision-memory query "why did we reject entry point discovery for adapters?"

The entry point discovery approach was rejected. [C1]
The entry point discovery approach adds packaging work before any external adapter exists. [C1]
The entry point discovery approach still requires runtime object validation after loading. [C1]

Sources
C1  DM-0005  docs/specs/0005-runtime-adapter-loading/rationale.md  Options considered
```

The citation points to one file and one section. You can open that file and read it.

## The state on 2026-08-12

**What works:**

- The tool reads decision documents, builds an index, and answers questions.
- Each answer has a correct citation. The citations are accurate.
- The tool refuses to answer when the documents have no answer.
- The search uses two methods together: keywords and meaning.
- A test harness measures answer quality against known questions.

**What does not work yet:**

- Answers come as many short sentences. The sentences are correct, but they are not smooth to read.
- Some correct answers get refused. This happens when a decision needs more than one sentence.
- The tool reads only one document format.
- You must have an OpenAI key.
- You must use the command line. There is no editor integration.

## What comes next

1. **Better answers.** This work is in progress. It corrects the two answer problems above.
2. **More formats.** The tool will read ADR and MADR documents. Then more projects can use it.
3. **Editor integration.** An agent in your editor will ask the questions for you. This is where the tool is most useful.

## Who should use it

Use the tool if your project already writes decision documents.

The tool is useful when you join a project, when you review code, and when you want to know if the team already rejected an idea.

Do not use the tool if your project has no decision documents. The tool reads history. It does not create history.

## More information

- [README](../README.md) tells you how to install and start the tool.
- [User guide](user-guide.md) gives the record format and the internal details.
