# GitAnonymizer

GitAnonymizer is a system that helps anonymize GitHub repositories for double-anonymous paper submissions. A public instance of GitAnonymizer is hosted at https://your-hostname/.

![screenshot](https://user-images.githubusercontent.com/5577568/217193282-42f608d3-2b46-4ebc-90df-772f248605be.png)


GitAnonymizer anonymizes the following:

- GitHub repository owner, organization, and name
- File and directory names
- File contents of all extensions, including markdown, text, Java, etc.

## Usage

### Public instance

**https://gitanonymizer-production.up.railway.app/**

### CLI

This CLI tool allows you to anonymize your GitHub repositories locally, generating an anonymized zip file based on your configuration settings.

```bash
# Install the GitAnonymizer CLI tool
npm install -g @GitAnonymizer/platform

# Run the GitAnonymizer CLI tool
GitAnonymizer
```

### Own instance

#### 1. Clone the repository

```bash
git clone https://github.com/your-org/GitAnonymizer
cd GitAnonymizer
npm i
```

#### 2. Configure OAuth/Tokens (optional for default login)

Create a `.env` file with the following contents:

```env
GITHUB_TOKEN=<GITHUB_TOKEN>
CLIENT_ID=<CLIENT_ID>
CLIENT_SECRET=<CLIENT_SECRET>
PORT=5000
APP_BASE_URL=http://localhost:5000
DB_USERNAME=
DB_PASSWORD=
AUTH_CALLBACK=http://localhost:5000/github/auth
APP_HOSTNAME=localhost
REDIS_URL=redis://redis:6379
MONGODB_URI=mongodb://<user>:<password>@mongodb:27017/production
```

- `GITHUB_TOKEN` can be generated here: https://github.com/settings/tokens/new with `repo` scope.
- `CLIENT_ID` and `CLIENT_SECRET` are the tokens are generated when you create a new GitHub app https://github.com/settings/applications/new.
- The callback of the GitHub app needs to be defined as `https://<host>/github/auth` (the same as defined in `AUTH_CALLBACK`).
- On Railway, set `APP_BASE_URL=https://<your-domain>`. If `RAILWAY_PUBLIC_DOMAIN` is available, callback/hostname can be inferred automatically.

#### 3. Start GitAnonymizer server

```bash
docker-compose up -d
```

#### 4. Go to GitAnonymizer

Go to http://localhost:5000. By default, GitAnonymizer uses port 5000. It can be changed in `docker-compose.yml`. I would recommand to put GitAnonymizer behind ngnix to handle the https certificates.

## What is the scope of anonymization?

In double-anonymous peer-review, the boundary of anonymization is the paper plus its online appendix, and only this, it's not the whole world. Googling any part of the paper or the online appendix can be considered as a deliberate attempt to break anonymity ([explanation](https://www.monperrus.net/martin/open-science-double-blind))

## How does it work?

GitAnonymizer either downloads the complete repository and anonymizes the content of the file or proxies the request to GitHub. In both cases, the original and anonymized versions of the file are cached on the server.

## Related tools

[gitmask](https://www.gitmask.com/) is a tool to anonymously contribute to a GitHub repository.

[blind-reviews](https://github.com/zombie/blind-reviews/) is a browser add-on that enables a person reviewing a GitHub pull request to hide identifying information about the person submitting it.

## See also

- [Open-science and double-anonymous Peer-Review](https://www.monperrus.net/martin/open-science-double-blind)
- [ACM Policy on Double-Blind Reviewing](https://dl.acm.org/journal/tods/DoubleBlindPolicy)


