import mongoose, { ConnectOptions } from "mongoose";
import Repository from "../core/Repository";
import config from "../config";
import AnonymizedRepositoryModel from "../core/model/anonymizedRepositories/anonymizedRepositories.model";
import AnonymousError from "../core/AnonymousError";
import AnonymizedPullRequestModel from "../core/model/anonymizedPullRequests/anonymizedPullRequests.model";
import PullRequest from "../core/PullRequest";

function getMongoConnectionConfig(): {
  uri: string;
  options: ConnectOptions;
} {
  if (config.MONGODB_URI) {
    return {
      uri: config.MONGODB_URI,
      options: {
        appName: "VeilMirror Server",
        compressors: "zstd",
      } as ConnectOptions,
    };
  }
  return {
    uri: `mongodb://${config.DB_USERNAME}:${config.DB_PASSWORD}@${config.DB_HOSTNAME}:27017/production`,
    options: {
      authSource: "admin",
      appName: "VeilMirror Server",
      compressors: "zstd",
    } as ConnectOptions,
  };
}

export const database = mongoose.connection;

export let isConnected = false;

export async function connect() {
  const mongo = getMongoConnectionConfig();
  mongoose.set("strictQuery", false);
  await mongoose.connect(mongo.uri, mongo.options);
  isConnected = true;

  // Remove deprecated conference data kept from older versions.
  await Promise.all([
    AnonymizedRepositoryModel.updateMany(
      { conference: { $exists: true } },
      { $unset: { conference: "" } }
    ),
    AnonymizedPullRequestModel.updateMany(
      { conference: { $exists: true } },
      { $unset: { conference: "" } }
    ),
  ]);
  try {
    await mongoose.connection.db?.dropCollection("conferences");
  } catch (error: any) {
    // ignore when collection does not exist
    if (error?.codeName !== "NamespaceNotFound") {
      console.warn("[db] could not drop conferences collection", error);
    }
  }

  return database;
}

export async function getRepository(repoId: string, opts: {} = {}) {
  if (!repoId || repoId == "undefined") {
    throw new AnonymousError("repo_not_found", {
      object: repoId,
      httpStatus: 404,
    });
  }
  const data = await AnonymizedRepositoryModel.findOne({ repoId }).collation({
    locale: "en",
    strength: 2,
  });
  if (!data)
    throw new AnonymousError("repo_not_found", {
      object: repoId,
      httpStatus: 404,
    });
  return new Repository(data);
}
export async function getPullRequest(pullRequestId: string) {
  if (!pullRequestId || pullRequestId == "undefined") {
    throw new AnonymousError("pull_request_not_found", {
      object: pullRequestId,
      httpStatus: 404,
    });
  }
  const data = await AnonymizedPullRequestModel.findOne({
    pullRequestId,
  });
  if (!data)
    throw new AnonymousError("pull_request_not_found", {
      object: pullRequestId,
      httpStatus: 404,
    });
  return new PullRequest(data);
}

