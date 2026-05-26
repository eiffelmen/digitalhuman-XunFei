// rem等比适配配置文件
// 基准大小
const baseSize = 14
// 设置 rem 函数
function setRem () {
  // 当前页面宽度相对于 1920宽的缩放比例，可根据自己需要修改。这里的1920是设计图的宽度
  const scale = document.documentElement.clientWidth / 1920;
  // 设置页面根节点字体大小
  document.documentElement.style.fontSize = baseSize * scale + 'px';
}
// 初始化
setRem()
// 改变窗口大小时重新设置 rem
window.addEventListener('resize',()=>{
  setRem()
})
