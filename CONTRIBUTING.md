# Contributing

## Commit messages

All commits must follow [Conventional Commits 1.0.0](https://www.conventionalcommits.org/en/v1.0.0/):

```text
type(optional-scope): imperative summary
```

Allowed types are `feat`, `fix`, `build`, `chore`, `ci`, `docs`, `perf`,
`refactor`, `revert`, `style`, and `test`. Use lowercase scopes containing
letters, digits, `.`, `_`, `/`, or `-`. Mark breaking changes with `!` before
the colon, for example `feat(api)!: require OTP challenge IDs`.

Enable repository hooks after cloning:

```powershell
git config core.hooksPath .githooks
```

The versioned `commit-msg` hook rejects nonconforming messages locally. Pull
request CI validates every commit in the branch as well.
