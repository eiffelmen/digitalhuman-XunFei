/*
  处理內联样式的缩放
  获取当前屏幕大小与1920的比列,计算大小，这里的1920还是看设计图的宽度
*/
export const getScaleByUI = (size) => {
  const scale = document.documentElement.clientWidth / 1920;
  return size * scale;
}
