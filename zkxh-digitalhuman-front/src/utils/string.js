function isChinese(character) {
  const regex = /[\u4E00-\u9FFF]/
  return regex.test(character)
}

function isEnglish(character) {
  const regex = /^[A-Za-z]+$/
  return regex.test(character)
}
export { isChinese, isEnglish }
