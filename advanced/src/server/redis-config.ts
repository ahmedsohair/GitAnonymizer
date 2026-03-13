import type { RedisClientOptions } from "redis";
import config from "../config";

export function getRedisClientOptions(): RedisClientOptions {
  if (config.REDIS_URL) {
    return {
      url: config.REDIS_URL,
    } as RedisClientOptions;
  }
  return {
    socket: {
      host: config.REDIS_HOSTNAME,
      port: Number(config.REDIS_PORT),
    },
  } as RedisClientOptions;
}

export function getRedisQueueConnection(): Record<string, any> {
  if (!config.REDIS_URL) {
    return {
      host: config.REDIS_HOSTNAME,
      port: Number(config.REDIS_PORT),
    };
  }
  try {
    const parsed = new URL(config.REDIS_URL);
    const connection: Record<string, any> = {
      host: parsed.hostname,
      port: Number(parsed.port || (parsed.protocol === "rediss:" ? 6380 : 6379)),
    };
    if (parsed.username) {
      connection.username = decodeURIComponent(parsed.username);
    }
    if (parsed.password) {
      connection.password = decodeURIComponent(parsed.password);
    }
    if (parsed.protocol === "rediss:") {
      connection.tls = {};
    }
    return connection;
  } catch (_error) {
    return {
      host: config.REDIS_HOSTNAME,
      port: Number(config.REDIS_PORT),
    };
  }
}
