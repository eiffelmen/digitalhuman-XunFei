// 获取 src/assets 目录下的资源
export const getAssetImgUrl = (url, path) => {
  if (!path) return new URL(`../assets/${url}`, import.meta.url).href;
  return new URL(`../assets/${path}/${url}`, import.meta.url).href;
}

// 获取 public 目录下的资源（兼容 Electron 环境）
export const getPublicUrl = (url) => {
  // 在 Electron 环境下，使用相对路径
  // public 目录的文件会被复制到 dist 根目录
  if (url.startsWith('/')) {
    return `.${url}`;
  }
  return url;
}