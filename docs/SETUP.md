# Setting up your own desk

Scriptorium is the framework. Your writing lives in a *separate private repo*
that mounts scriptorium as a submodule. The fastest path is the scaffolding tool;
the manual steps are below it so you can see what it does.

## The one-liner

```bash
# from anywhere; point it at where you want your desk
path/to/scriptorium/tools/new-desk ~/code/writing-desk
```

By default the new desk mounts scriptorium from its public URL. To develop
against a **local** scriptorium checkout (before it's pushed anywhere), pass it:

```bash
tools/new-desk ~/code/writing-desk --framework /Users/you/code/scriptorium
```

Then create the private GitHub repo when you're ready:

```bash
cd ~/code/writing-desk
gh repo create <you>/writing-desk --private --source=. --remote=origin
git push -u origin main
```

## What it sets up (the manual version)

### 1. The instance repo

```bash
mkdir writing-desk && cd writing-desk
git init
```

### 2. Scriptorium as a submodule

```bash
git submodule add https://github.com/<you>/scriptorium.git framework
git commit -m "Add scriptorium framework submodule"
```

### 3. Wire the shared skills in

Claude Code discovers skills from `.claude/skills/`. Symlink the framework's
skills so they stay a single source of truth:

```bash
mkdir -p .claude/skills
for s in draft critique tune-style whats-on-the-desk; do
  ln -s "../../framework/skills/$s" ".claude/skills/$s"
done
```

Private skills tuned to you live as **real files** under `.claude/skills/`, not
in the framework.

### 4. Bring in a style to tune

Copy a starter style out of the framework into your instance, where you'll tune
it privately:

```bash
mkdir -p styles
cp -R framework/styles/plain-english styles/my-voice
```

Your trained styles live in the instance and never go back into the framework.

### 5. Behavior file and dashboard

```bash
cp framework/CLAUDE.md ./CLAUDE.md   # then adjust to taste
```

Create a top-level `DASHBOARD.md` with one block per piece, and start your first
piece:

```bash
mkdir -p pieces/<name>
cp -R framework/templates/piece/. pieces/<name>/
```

## Keeping the framework up to date

```bash
git submodule update --remote framework
git commit -am "Update scriptorium framework"
```

## Cloning your desk elsewhere

```bash
git clone --recurse-submodules <your instance repo>
# or, after a plain clone:
git submodule update --init
```
