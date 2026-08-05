export function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.rel = 'noopener'
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

export function downloadJson(data, filename) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
  downloadBlob(blob, filename)
}

export function downloadText(text, filename, type = 'text/plain') {
  const blob = new Blob([text], { type })
  downloadBlob(blob, filename)
}

export function lessonToMarkdown(lesson) {
  const lines = [`# ${lesson.topic || 'Lesson'}`, '']
  if (lesson.overview) lines.push('## Overview', lesson.overview, '')
  if (lesson.learning_objectives?.length) {
    lines.push('## Learning Objectives', ...lesson.learning_objectives.map((item) => `- ${item}`), '')
  }
  for (const section of lesson.sections || []) {
    lines.push(`## ${section.heading}`, section.content || '')
    if (section.example) lines.push(`*Example:* ${section.example}`)
    lines.push('')
  }
  if (lesson.summary) lines.push('## Summary', lesson.summary, '')
  return lines.join('\n')
}

export function flashcardsToHtml(data) {
  const cards = (data.cards || []).map((card, index) => `
    <div class="card" onclick="this.classList.toggle('flipped')">
      <div class="inner">
        <div class="face front">
          <p class="eyebrow">Card ${index + 1} &middot; Click to flip</p>
          <h2>${card.front}</h2>
        </div>
        <div class="face back">
          <p class="eyebrow">Answer</p>
          <p class="answer-text">${card.back}</p>
        </div>
      </div>
    </div>
  `).join('')
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>${data.title || 'Flashcards'}</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: Inter, Arial, sans-serif;
      background: linear-gradient(135deg, #081226 0%, #10243f 45%, #0f766e 100%);
      min-height: 100vh;
      padding: 40px 24px;
      color: #fff;
    }
    h1 { font-size: 2.2rem; text-align: center; margin-bottom: 8px; }
    .subtitle { color: #cbd5e1; text-align: center; margin-bottom: 36px; font-size: 1rem; }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
      gap: 28px;
      max-width: 1200px;
      margin: 0 auto;
    }
    .card {
      height: 280px;
      cursor: pointer;
      perspective: 1200px;
    }
    .card:hover .inner { transform: translateY(-4px); }
    .card.flipped .inner { transform: rotateY(180deg) !important; }
    .inner {
      position: relative;
      width: 100%;
      height: 100%;
      transition: transform 0.65s cubic-bezier(.4,0,.2,1);
      transform-style: preserve-3d;
      will-change: transform;
    }
    .face {
      position: absolute;
      inset: 0;
      border-radius: 20px;
      padding: 28px 24px;
      display: flex;
      flex-direction: column;
      justify-content: center;
      align-items: center;
      text-align: center;
      backface-visibility: hidden;
      -webkit-backface-visibility: hidden;
      box-shadow: 0 20px 50px rgba(0,0,0,0.35);
      border: 1px solid rgba(255,255,255,0.15);
    }
    .front {
      background: linear-gradient(160deg, rgba(255,255,255,0.12), rgba(45,212,191,0.18));
    }
    .back {
      background: linear-gradient(160deg, rgba(15,118,110,0.9), rgba(15,23,42,0.95));
      transform: rotateY(180deg);
    }
    .eyebrow {
      position: absolute;
      top: 18px;
      left: 50%;
      transform: translateX(-50%);
      text-transform: uppercase;
      letter-spacing: 0.15em;
      font-size: 0.7rem;
      color: #99f6e4;
      white-space: nowrap;
    }
    .face h2 { font-size: 1.25rem; line-height: 1.5; color: #f1f5f9; }
    .answer-text { font-size: 1.05rem; line-height: 1.75; color: #ecfeff; }
  </style>
</head>
<body>
  <h1>${data.title || 'Flashcards'}</h1>
  <p class="subtitle">Click any card to flip it and reveal the answer.</p>
  <div class="grid">${cards}</div>
</body>
</html>`
}


export function quizToMarkdown(quiz) {
  const lines = [`# ${quiz.title || 'Quiz'}`, `Difficulty: ${quiz.difficulty || 'Medium'}`, '']
  for (const [index, question] of (quiz.questions || []).entries()) {
    lines.push(`## Question ${index + 1}`, question.question || '')
    for (const option of question.options || []) lines.push(`- ${option}`)
    lines.push(`**Answer:** ${question.answer || ''}`, '')
  }
  return lines.join('\n')
}
