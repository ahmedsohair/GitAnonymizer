import * as express from "express";
import { ensureAuthenticated } from "./connection";

import {
  getPullRequest,
  getUser,
  handleError,
  isOwnerOrAdmin,
} from "./route-utils";
import AnonymousError from "../../core/AnonymousError";
import { IAnonymizedPullRequestDocument } from "../../core/model/anonymizedPullRequests/anonymizedPullRequests.types";
import PullRequest from "../../core/PullRequest";
import AnonymizedPullRequestModel from "../../core/model/anonymizedPullRequests/anonymizedPullRequests.model";
import { RepositoryStatus } from "../../core/types";

const router = express.Router();

// user needs to be connected for all user API
router.use(ensureAuthenticated);

// refresh pullRequest
router.post(
  "/:pullRequestId/refresh",
  async (req: express.Request, res: express.Response) => {
    try {
      const pullRequest = await getPullRequest(req, res, { nocheck: true });
      if (!pullRequest) return;

      const user = await getUser(req);
      isOwnerOrAdmin([pullRequest.owner.id], user);
      await pullRequest.updateIfNeeded({ force: true });
      res.json({ status: pullRequest.status });
    } catch (error) {
      handleError(error, res, req);
    }
  }
);

// delete a pullRequest
router.delete(
  "/:pullRequestId/",
  async (req: express.Request, res: express.Response) => {
    const pullRequest = await getPullRequest(req, res, { nocheck: true });
    if (!pullRequest) return;
    try {
      if (pullRequest.status == "removed")
        throw new AnonymousError("is_removed", {
          object: req.params.pullRequestId,
          httpStatus: 410,
        });
      const user = await getUser(req);
      isOwnerOrAdmin([pullRequest.owner.id], user);
      await pullRequest.remove();
      return res.json({ status: pullRequest.status });
    } catch (error) {
      handleError(error, res, req);
    }
  }
);

router.get(
  "/:owner/:repository/:pullRequestId",
  async (req: express.Request, res: express.Response) => {
    const user = await getUser(req);
    try {
      const pullRequest = new PullRequest(
        new AnonymizedPullRequestModel({
          owner: user.id,
          source: {
            pullRequestId: parseInt(req.params.pullRequestId),
            repositoryFullName: `${req.params.owner}/${req.params.repository}`,
          },
        })
      );
      pullRequest.owner = user;
      await pullRequest.download();
      res.json(pullRequest.toJSON());
    } catch (error) {
      handleError(error, res, req);
    }
  }
);

// get pullRequest information
router.get(
  "/:pullRequestId/",
  async (req: express.Request, res: express.Response) => {
    try {
      const pullRequest = await getPullRequest(req, res, { nocheck: true });
      if (!pullRequest) return;

      const user = await getUser(req);
      isOwnerOrAdmin([pullRequest.owner.id], user);
      res.json(pullRequest.toJSON());
    } catch (error) {
      handleError(error, res, req);
    }
  }
);

function randomSuffix(size = 5): string {
  const alphabet = "abcdefghijklmnopqrstuvwxyz0123456789";
  let out = "";
  for (let i = 0; i < size; i++) {
    out += alphabet[Math.floor(Math.random() * alphabet.length)];
  }
  return out;
}

function sanitizePullRequestIdPrefix(input: string): string {
  const sanitized = (input || "")
    .toLowerCase()
    .replace(/[^a-z0-9\-_]/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-+|-+$/g, "");
  if (sanitized.length >= 3) {
    return sanitized;
  }
  return "pr";
}

async function generatePullRequestId(base: string): Promise<string> {
  const prefix = sanitizePullRequestIdPrefix(base);
  for (let i = 0; i < 50; i++) {
    const candidate = `${prefix}-${randomSuffix(5)}`;
    const existing = await AnonymizedPullRequestModel.findOne({
      pullRequestId: candidate,
    });
    if (!existing) {
      return candidate;
    }
  }
  throw new AnonymousError("pullRequestId_already_used", {
    httpStatus: 400,
    object: base,
  });
}

function validateNewPullRequest(pullRequestUpdate: any): void {
  const validCharacters = /^[0-9a-zA-Z\-\_]+$/;
  if (pullRequestUpdate.pullRequestId) {
    if (
      !pullRequestUpdate.pullRequestId.match(validCharacters) ||
      pullRequestUpdate.pullRequestId.length < 3
    ) {
      throw new AnonymousError("invalid_pullRequestId", {
        object: pullRequestUpdate,
        httpStatus: 400,
      });
    }
  }
  if (!pullRequestUpdate.source || !pullRequestUpdate.source.repositoryFullName) {
    throw new AnonymousError("repository_not_specified", {
      object: pullRequestUpdate,
      httpStatus: 400,
    });
  }
  if (!pullRequestUpdate.source.pullRequestId) {
    throw new AnonymousError("pullRequestId_not_specified", {
      object: pullRequestUpdate,
      httpStatus: 400,
    });
  }
  if (
    parseInt(pullRequestUpdate.source.pullRequestId) !=
    pullRequestUpdate.source.pullRequestId
  ) {
    throw new AnonymousError("pullRequestId_is_not_a_number", {
      object: pullRequestUpdate,
      httpStatus: 400,
    });
  }
  if (!pullRequestUpdate.options) {
    throw new AnonymousError("options_not_provided", {
      object: pullRequestUpdate,
      httpStatus: 400,
    });
  }
  if (!Array.isArray(pullRequestUpdate.terms)) {
    throw new AnonymousError("invalid_terms_format", {
      object: pullRequestUpdate,
      httpStatus: 400,
    });
  }
}

function updatePullRequestModel(
  model: IAnonymizedPullRequestDocument,
  pullRequestUpdate: any
) {
  model.options = {
    terms: pullRequestUpdate.terms,
    expirationMode: pullRequestUpdate.options.expirationMode,
    expirationDate: pullRequestUpdate.options.expirationDate
      ? new Date(pullRequestUpdate.options.expirationDate)
      : undefined,
    update: pullRequestUpdate.options.update,
    image: pullRequestUpdate.options.image,
    link: pullRequestUpdate.options.link,
    body: pullRequestUpdate.options.body,
    title: pullRequestUpdate.options.title,
    username: pullRequestUpdate.options.username,
    origin: pullRequestUpdate.options.origin,
    diff: pullRequestUpdate.options.diff,
    comments: pullRequestUpdate.options.comments,
    date: pullRequestUpdate.options.date,
  };
}

// update a pullRequest
router.post(
  "/:pullRequestId/",
  async (req: express.Request, res: express.Response) => {
    try {
      const pullRequest = await getPullRequest(req, res, { nocheck: true });
      if (!pullRequest) return;
      const user = await getUser(req);

      isOwnerOrAdmin([pullRequest.owner.id], user);
      const pullRequestUpdate = req.body;
      pullRequestUpdate.pullRequestId = pullRequest.model.pullRequestId;
      validateNewPullRequest(pullRequestUpdate);
      pullRequest.model.anonymizeDate = new Date();

      updatePullRequestModel(pullRequest.model, pullRequestUpdate);
      await pullRequest.updateStatus(RepositoryStatus.PREPARING);
      await pullRequest.updateIfNeeded({ force: true });
      res.json(pullRequest.toJSON());
    } catch (error) {
      return handleError(error, res, req);
    }
  }
);

// add pullRequest
router.post("/", async (req: express.Request, res: express.Response) => {
  const user = await getUser(req);
  const pullRequestUpdate = req.body;

  try {
    if (!pullRequestUpdate.pullRequestId) {
      const [_, repository = "pr"] = (
        pullRequestUpdate.source?.repositoryFullName || ""
      ).split("/");
      pullRequestUpdate.pullRequestId = await generatePullRequestId(repository);
    } else {
      const existing = await AnonymizedPullRequestModel.findOne({
        pullRequestId: pullRequestUpdate.pullRequestId,
      });
      if (existing) {
        throw new AnonymousError("pullRequestId_already_used", {
          httpStatus: 400,
          object: pullRequestUpdate,
        });
      }
    }

    validateNewPullRequest(pullRequestUpdate);

    const pullRequest = new PullRequest(
      new AnonymizedPullRequestModel({
        owner: user.id,
        options: pullRequestUpdate.options,
      })
    );

    pullRequest.model.pullRequestId = pullRequestUpdate.pullRequestId;
    pullRequest.model.anonymizeDate = new Date();
    pullRequest.model.owner = user.id;

    updatePullRequestModel(pullRequest.model, pullRequestUpdate);
    pullRequest.source.accessToken = user.accessToken;
    pullRequest.source.pullRequestId = pullRequestUpdate.source.pullRequestId;
    pullRequest.source.repositoryFullName =
      pullRequestUpdate.source.repositoryFullName;

    await pullRequest.anonymize();
    res.send(pullRequest.toJSON());
  } catch (error) {
    if (
      error instanceof Error &&
      error.message.indexOf(" duplicate key") > -1
    ) {
      return handleError(
        new AnonymousError("pullRequestId_already_used", {
          httpStatus: 400,
          cause: error,
          object: pullRequestUpdate,
        }),
        res,
        req
      );
    }
    return handleError(error, res, req);
  }
});

export default router;
