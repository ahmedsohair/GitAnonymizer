import * as schedule from "node-schedule";
import AnonymizedRepositoryModel from "../core/model/anonymizedRepositories/anonymizedRepositories.model";
import Repository from "../core/Repository";

export function repositoryStatusCheck() {
  // check every 6 hours the status of the repositories
  const job = schedule.scheduleJob("0 */6 * * *", async () => {
    console.log("[schedule] Check repository status and unused repositories");
    (
      await AnonymizedRepositoryModel.find({
        status: { $eq: "ready" },
        isReseted: { $eq: false },
      })
    ).forEach((data) => {
      const repo = new Repository(data);
      try {
        repo.check();
      } catch (error) {
        console.log(`Repository ${repo.repoId} is expired`);
      }
      const fourMonthAgo = new Date();
      fourMonthAgo.setMonth(fourMonthAgo.getMonth() - 4);

      if (repo.model.lastView < fourMonthAgo) {
        repo.removeCache().then(() => {
          console.log(
            `Repository ${repo.repoId} not visited for 4 months remove the cached files`
          );
        });
      }
    });
  });
}
