import { createClient } from "redis";
import * as passport from "passport";
import * as session from "express-session";
import RedisStore from "connect-redis";
import * as OAuth2Strategy from "passport-oauth2";
import { Profile, Strategy } from "passport-github2";
import * as express from "express";

import config from "../../config";
import UserModel from "../../core/model/users/users.model";
import { IUserDocument } from "../../core/model/users/users.types";
import AnonymousError from "../../core/AnonymousError";
import AnonymizedPullRequestModel from "../../core/model/anonymizedPullRequests/anonymizedPullRequests.model";
import { getRedisClientOptions } from "../redis-config";

export function ensureAuthenticated(
  req: express.Request,
  res: express.Response,
  next: express.NextFunction
) {
  if (req.isAuthenticated()) {
    return next();
  }
  res.status(401).json({ error: "not_connected" });
}

type GitHubOAuthConfig = {
  clientId: string;
  clientSecret: string;
};

const SESSION_GITHUB_OAUTH_KEY = "githubOAuthConfig";
const SESSION_GITHUB_STRATEGY_KEY = "githubOAuthStrategy";
const OAUTH_PLACEHOLDER_VALUES = new Set([
  "",
  "CLIENT_ID",
  "CLIENT_SECRET",
  "placeholder_client_id",
  "placeholder_client_secret",
]);

function getSession(req: express.Request): Record<string, any> | null {
  return (req.session as unknown as Record<string, any>) || null;
}

function getSessionOAuthConfig(req: express.Request): GitHubOAuthConfig | null {
  const session = getSession(req);
  if (!session) {
    return null;
  }
  const raw = session[SESSION_GITHUB_OAUTH_KEY] as
    | GitHubOAuthConfig
    | undefined;
  if (
    raw &&
    typeof raw.clientId === "string" &&
    typeof raw.clientSecret === "string" &&
    raw.clientId.trim() &&
    raw.clientSecret.trim()
  ) {
    return {
      clientId: raw.clientId.trim(),
      clientSecret: raw.clientSecret.trim(),
    };
  }
  return null;
}

function getOAuthConfigForRequest(req: express.Request): GitHubOAuthConfig {
  return (
    getSessionOAuthConfig(req) || {
      clientId: config.CLIENT_ID,
      clientSecret: config.CLIENT_SECRET,
    }
  );
}

function parseOAuthConfigFromRequest(
  req: express.Request
): GitHubOAuthConfig | null {
  const body = (req.body || {}) as Record<string, unknown>;
  const query = (req.query || {}) as Record<string, unknown>;

  const bodyClientId = body.client_id;
  const bodyClientSecret = body.client_secret;
  const queryClientId = query.client_id;
  const queryClientSecret = query.client_secret;

  const clientIdRaw =
    typeof bodyClientId === "string"
      ? bodyClientId
      : typeof queryClientId === "string"
        ? queryClientId
        : "";
  const clientSecretRaw =
    typeof bodyClientSecret === "string"
      ? bodyClientSecret
      : typeof queryClientSecret === "string"
        ? queryClientSecret
        : "";

  const clientId = clientIdRaw.trim();
  const clientSecret = clientSecretRaw.trim();

  if (!clientId && !clientSecret) {
    return null;
  }
  if (!clientId || !clientSecret) {
    throw new AnonymousError("invalid_oauth_config", {
      httpStatus: 400,
      object: {
        reason: "Both client_id and client_secret are required",
      },
    });
  }
  return {
    clientId,
    clientSecret,
  };
}

function isConfiguredOAuthConfig(oauth: GitHubOAuthConfig): boolean {
  const clientId = oauth.clientId.trim();
  const clientSecret = oauth.clientSecret.trim();
  if (!clientId || !clientSecret) {
    return false;
  }
  if (
    OAUTH_PLACEHOLDER_VALUES.has(clientId) ||
    OAUTH_PLACEHOLDER_VALUES.has(clientSecret)
  ) {
    return false;
  }
  return true;
}

function upsertGitHubStrategy(name: string, oauth: GitHubOAuthConfig) {
  passport.use(
    name,
    new Strategy(
      {
        clientID: oauth.clientId,
        clientSecret: oauth.clientSecret,
        callbackURL: config.AUTH_CALLBACK,
        passReqToCallback: true,
      },
      verify
    )
  );
}

function resolveStrategy(req: express.Request): string {
  const oauth = getOAuthConfigForRequest(req);
  const isDefaultOauth =
    oauth.clientId === config.CLIENT_ID &&
    oauth.clientSecret === config.CLIENT_SECRET;

  if (isDefaultOauth) {
    if (!isConfiguredOAuthConfig(oauth)) {
      throw new AnonymousError("platform_oauth_not_configured", {
        httpStatus: 503,
        object: {
          reason:
            "Platform GitHub OAuth is not configured. Set ADVANCED_GITHUB_CLIENT_ID and ADVANCED_GITHUB_CLIENT_SECRET.",
        },
      });
    }
    upsertGitHubStrategy("github", oauth);
    return "github";
  }

  const safeSessionId = (req.sessionID || "default").replace(
    /[^a-zA-Z0-9_-]/g,
    "_"
  );
  const strategyName = `github-${safeSessionId}`;
  upsertGitHubStrategy(strategyName, oauth);

  const session = getSession(req);
  if (session) {
    session[SESSION_GITHUB_STRATEGY_KEY] = strategyName;
  }

  return strategyName;
}

const verify = async (
  req: express.Request,
  accessToken: string,
  refreshToken: string,
  profile: Profile,
  done: OAuth2Strategy.VerifyCallback
): Promise<void> => {
  let user: IUserDocument | null = null;
  try {
    user = await UserModel.findOne({ "externalIDs.github": profile.id });
    if (user) {
      user.accessTokens.github = accessToken;
      await AnonymizedPullRequestModel.updateMany(
        { owner: user._id },
        { "source.accessToken": accessToken }
      );
    } else {
      const photo = profile.photos ? profile.photos[0]?.value : null;
      user = new UserModel({
        username: profile.username,
        accessTokens: {
          github: accessToken,
        },
        externalIDs: {
          github: profile.id,
        },
        emails: profile.emails?.map((email) => {
          return { email: email.value, default: false };
        }),
        photo,
      });
      if (user.emails?.length) user.emails[0].default = true;
    }
    if (!user.accessTokenDates) {
      user.accessTokenDates = {
        github: new Date(),
      };
    } else {
      user.accessTokenDates.github = new Date();
    }

    // Persist the OAuth app used for this login so token refresh can use it.
    const oauthConfig = getOAuthConfigForRequest(req);
    if (!user.oauthApps) {
      user.oauthApps = {
        github: oauthConfig,
      };
    } else {
      user.oauthApps.github = oauthConfig;
    }

    await user.save();
  } catch (error) {
    console.error(error);
    throw new AnonymousError("unable_to_connect_user", {
      httpStatus: 500,
      object: profile,
      cause: error as Error,
    });
  } finally {
    done(null, {
      username: profile.username,
      accessToken,
      refreshToken,
      profile,
      user,
    });
  }
};

const defaultOAuthConfig = {
  clientId: config.CLIENT_ID,
  clientSecret: config.CLIENT_SECRET,
};

if (isConfiguredOAuthConfig(defaultOAuthConfig)) {
  upsertGitHubStrategy("github", defaultOAuthConfig);
}

passport.serializeUser((user: Express.User, done) => {
  done(null, user);
});

passport.deserializeUser((user: Express.User, done) => {
  done(null, user);
});

export function initSession() {
  const redisClient = createClient({
    ...getRedisClientOptions(),
    legacyMode: false,
  });
  redisClient.on("error", (err) => console.log("Redis Client Error", err));
  redisClient.connect();
  const redisStore = new RedisStore({
    client: redisClient,
    prefix: "vm_session:",
  });

  return session({
    secret: config.SESSION_SECRET,
    store: redisStore,
    saveUninitialized: false,
    resave: false,
  });
}

export const router = express.Router();

function loginHandler(
  req: express.Request,
  res: express.Response,
  next: express.NextFunction
) {
  try {
    const provided = parseOAuthConfigFromRequest(req);
    const session = getSession(req);

    if (provided && session) {
      session[SESSION_GITHUB_OAUTH_KEY] = provided;
    }

    const strategyName = resolveStrategy(req);
    return passport.authenticate(strategyName, { scope: ["repo"] })(
      req,
      res,
      next
    );
  } catch (error) {
    if (error instanceof AnonymousError) {
      return res.status(error.httpStatus || 400).json({ error: error.message });
    }
    return next(error);
  }
}

router.get("/login", loginHandler);
router.post("/login", loginHandler);

router.get(
  "/auth",
  (
    req: express.Request,
    res: express.Response,
    next: express.NextFunction
  ) => {
    const session = getSession(req);
    const strategyName =
      (session && session[SESSION_GITHUB_STRATEGY_KEY]) || resolveStrategy(req);
    return passport.authenticate(strategyName, { failureRedirect: "/" })(
      req,
      res,
      next
    );
  },
  function (req: express.Request, res: express.Response) {
    const session = getSession(req);
    if (session) {
      delete session[SESSION_GITHUB_STRATEGY_KEY];
    }
    res.redirect("/");
  }
);

