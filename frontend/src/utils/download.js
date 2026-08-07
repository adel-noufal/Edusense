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


export function lessonToHtml(lesson) {
  const objectives = (lesson.learning_objectives || []).map(o => `<li style="margin-bottom: 8px; font-weight: 600; color: #0f766e;">✓ ${o}</li>`).join('')
  const sections = (lesson.sections || []).map((s, i) => `
    <div style="margin-bottom: 28px; padding: 20px; background: #ffffff; border-radius: 12px; border: 1px solid #e2e8f0; border-left: 6px solid #0f766e; box-shadow: 0 4px 12px rgba(0,0,0,0.03);">
      <h3 style="color: #0f766e; margin-top: 0; font-size: 1.3em; font-weight: 800;">${s.heading}</h3>
      <p style="line-height: 1.8; color: #334155; font-size: 1em; margin: 12px 0;">${s.content}</p>
      ${s.example ? `
        <div style="margin-top: 14px; padding: 12px 16px; background: #f0fdf4; border-radius: 8px; border: 1px solid #bbf7d0;">
          <p style="font-size: 0.85em; text-transform: uppercase; font-weight: 800; color: #166534; margin: 0 0 4px 0;">Practical Case Study & Example</p>
          <p style="margin: 0; color: #15803d; font-size: 0.95em; line-height: 1.6;">${s.example}</p>
        </div>` : ''}
    </div>
  `).join('')

  const slides = (lesson.slides || []).map((slide, i) => `
    <div style="margin-bottom: 20px; padding: 18px; background: #f8fafc; border-radius: 10px; border: 1px solid #cbd5e1; page-break-inside: avoid;">
      <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #e2e8f0; padding-bottom: 8px; margin-bottom: 12px;">
        <h4 style="margin: 0; color: #0369a1; font-size: 1.1em; font-weight: 800;">Slide ${i + 1}: ${slide.title}</h4>
        <span style="font-size: 0.75em; background: #e0f2fe; color: #0369a1; padding: 3px 8px; border-radius: 12px; font-weight: bold;">Presentation Slide</span>
      </div>
      <p style="margin: 0 0 10px 0; color: #1e293b; line-height: 1.7; whitespace: pre-line;">${slide.content}</p>
      ${slide.diagram ? `<p style="font-size: 0.85em; color: #0284c7; background: #e0f2fe; padding: 8px 12px; border-radius: 6px; margin-top: 8px; font-weight: 600;">📐 Diagram Blueprint: ${slide.diagram}</p>` : ''}
      ${slide.notes ? `<p style="font-size: 0.85em; color: #475569; font-style: italic; background: #f1f5f9; padding: 8px 12px; border-radius: 6px; margin-top: 8px;">🗣️ Instructor Notes: ${slide.notes}</p>` : ''}
    </div>
  `).join('')

  return `<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>${lesson.topic || 'EduSense Master Lesson Plan'}</title>
  <style>
    @media print {
      body { margin: 0; padding: 20px; font-size: 12pt; }
      .no-print { display: none !important; }
      .page-break { page-break-before: always; }
    }
    body { font-family: 'Segoe UI', system-ui, -apple-system, sans-serif; margin: 40px auto; color: #0f172a; max-width: 900px; padding: 20px; line-height: 1.6; }
    .header-box { background: linear-gradient(135deg, #0f766e 0%, #0369a1 100%); color: #ffffff; padding: 36px 30px; border-radius: 16px; margin-bottom: 30px; }
    .header-box h1 { margin: 0 0 10px 0; font-size: 2.4em; font-weight: 900; letter-spacing: -0.02em; }
    .header-box p { margin: 0; color: #ccfbf1; font-size: 1.05em; }
    .section-title { color: #0369a1; border-bottom: 2px solid #e2e8f0; padding-bottom: 8px; font-size: 1.4em; font-weight: 800; margin-top: 32px; }
    ul { list-style-type: none; padding-left: 0; }
  </style>
</head>
<body>
  <div className="no-print" style="margin-bottom: 20px; text-align: right;">
    <button onclick="window.print()" style="background: #0f766e; color: #fff; border: none; padding: 10px 20px; border-radius: 8px; font-weight: bold; cursor: pointer;">🖨️ Print / Save as PDF</button>
  </div>

  <div class="header-box">
    <p style="text-transform: uppercase; tracking: 0.15em; font-size: 0.8em; font-weight: 800; color: #99f6e4;">EduSense Master Lesson Resource</p>
    <h1>${lesson.topic || 'Lesson Plan'}</h1>
    <p>${lesson.duration || 60} Minutes &middot; ${lesson.style || 'Interactive Masterclass'} &middot; ${lesson.language || 'English'}</p>
  </div>

  ${lesson.overview ? `
    <div style="background: #f8fafc; padding: 20px; border-radius: 12px; border: 1px solid #cbd5e1; margin-bottom: 24px;">
      <h2 style="margin-top: 0; color: #0f766e; font-size: 1.2em; font-weight: 800;">Executive Overview</h2>
      <p style="font-size: 1.05em; line-height: 1.8; color: #334155; margin: 0;">${lesson.overview}</p>
    </div>` : ''}
  
  ${objectives ? `<h2 class="section-title">Learning Objectives</h2><ul style="background: #f0fdf4; padding: 20px; border-radius: 12px; border: 1px solid #bbf7d0;">${objectives}</ul>` : ''}
  
  ${sections ? `<h2 class="section-title">Core Curriculum Sections</h2>${sections}` : ''}
  
  ${slides ? `<h2 class="section-title">Presentation Slide Outline</h2>${slides}` : ''}
  
  ${lesson.summary ? `
    <h2 class="section-title">Executive Summary & Key Synthesis</h2>
    <div style="background: #e0f2fe; padding: 20px; border-radius: 12px; border: 1px solid #bae6fd;">
      <p style="margin: 0; font-size: 1.05em; line-height: 1.8; color: #0369a1;">${lesson.summary}</p>
    </div>` : ''}
</body>
</html>`
}

export function downloadLessonAsDoc(lesson, filename) {
  const html = lessonToHtml(lesson)
  const blob = new Blob(['\ufeff', html], { type: 'application/msword' })
  downloadBlob(blob, filename.endsWith('.doc') || filename.endsWith('.docx') ? filename : `${filename}.doc`)
}

export function downloadLessonAsHtml(lesson, filename) {
  const html = lessonToHtml(lesson)
  downloadText(html, filename.endsWith('.html') ? filename : `${filename}.html`, 'text/html')
}

export function downloadLessonAsPdf(lesson, filename) {
  const html = lessonToHtml(lesson)
  const win = window.open('', '_blank')
  if (win) {
    win.document.write(html)
    win.document.close()
    setTimeout(() => { win.print() }, 500)
  } else {
    downloadText(html, `${filename || 'lesson'}.html`, 'text/html')
  }
}

export function downloadLessonAsPptxHtml(lesson, filename) {
  const slidesHtml = (lesson.slides || []).map((slide, i) => `
    <div style="width: 100%; height: 540px; background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%); color: #ffffff; border-radius: 16px; padding: 40px; box-sizing: border-box; display: flex; flex-direction: column; justify-content: space-between; margin-bottom: 30px; page-break-after: always; box-shadow: 0 10px 30px rgba(0,0,0,0.3);">
      <div>
        <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid rgba(255,255,255,0.15); padding-bottom: 12px; margin-bottom: 24px;">
          <h2 style="margin: 0; color: #2dd4bf; font-size: 1.8em; font-weight: 900;">${slide.title}</h2>
          <span style="font-size: 0.9em; color: #94a3b8; font-weight: bold;">Slide ${i + 1} / ${(lesson.slides || []).length}</span>
        </div>
        <div style="font-size: 1.2em; line-height: 1.8; color: #f1f5f9; whitespace: pre-line;">
          ${slide.content}
        </div>
      </div>
      ${slide.diagram ? `
        <div style="background: rgba(45, 212, 191, 0.1); border: 1px solid rgba(45, 212, 191, 0.3); padding: 14px 20px; border-radius: 10px;">
          <p style="margin: 0; font-size: 0.9em; color: #2dd4bf; font-weight: bold;">📐 Visual Concept: ${slide.diagram}</p>
        </div>` : ''}
    </div>
  `).join('')

  const html = `<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>${lesson.topic || 'Presentation Slides'}</title>
  <style>body { font-family: Inter, Arial, sans-serif; background: #090d16; margin: 40px auto; max-width: 960px; padding: 20px; }</style>
</head>
<body>
  <div style="text-align: center; margin-bottom: 24px; color: #fff;">
    <h1 style="color: #2dd4bf;">${lesson.topic || 'Presentation Slides'}</h1>
    <p style="color: #94a3b8;">Presentation Deck &middot; Click Print to export as PDF Presentation</p>
  </div>
  ${slidesHtml}
</body>
</html>`
  downloadText(html, filename.endsWith('.html') || filename.endsWith('.pptx') ? filename : `${filename}.pptx.html`, 'text/html')
}

export function quizToHtml(quiz) {
  const questions = (quiz.questions || []).map((q, i) => `
    <div style="margin-bottom: 24px; padding: 20px; background: #ffffff; border-radius: 12px; border: 1px solid #cbd5e1; box-shadow: 0 2px 8px rgba(0,0,0,0.02);">
      <p style="font-weight: 800; font-size: 1.15em; color: #0f172a; margin-top: 0;">${i + 1}. ${q.question}</p>
      ${q.options ? `
        <ul style="list-style: none; padding-left: 0; margin: 14px 0;">
          ${q.options.map(o => `<li style="padding: 10px 16px; background: #f8fafc; margin: 6px 0; border-radius: 8px; border: 1px solid #e2e8f0; font-size: 0.95em;">${o}</li>`).join('')}
        </ul>` : ''}
      <div style="margin-top: 14px; padding: 12px; background: #f0fdf4; border-radius: 8px; border-left: 4px solid #10b981;">
        <p style="color: #047857; font-weight: 800; margin: 0;">Correct Answer: ${q.answer}</p>
        ${q.explanation ? `<p style="color: #065f46; font-size: 0.9em; margin: 6px 0 0 0; line-height: 1.6;">Explanation: ${q.explanation}</p>` : ''}
      </div>
    </div>
  `).join('')

  return `<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>${quiz.title || 'Quiz Assessment'}</title>
  <style>
    @media print { body { padding: 0; font-size: 11pt; } .no-print { display: none; } }
    body { font-family: Inter, Arial, sans-serif; margin: 40px auto; max-width: 850px; color: #0f172a; padding: 20px; }
  </style>
</head>
<body>
  <div className="no-print" style="margin-bottom: 20px; text-align: right;">
    <button onclick="window.print()" style="background: #0f766e; color: #fff; border: none; padding: 10px 20px; border-radius: 8px; font-weight: bold; cursor: pointer;">🖨️ Print / Save as PDF</button>
  </div>
  <div style="background: #0f766e; color: #fff; padding: 24px; border-radius: 12px; margin-bottom: 28px;">
    <h1 style="margin: 0 0 6px 0; font-size: 2em; font-weight: 900;">${quiz.title || 'Quiz Assessment'}</h1>
    <p style="margin: 0; color: #99f6e4;">Difficulty: ${quiz.difficulty || 'Medium'} &middot; Total Questions: ${(quiz.questions || []).length}</p>
  </div>
  ${questions}
</body>
</html>`
}

export function downloadQuizAsDoc(quiz, filename) {
  const html = quizToHtml(quiz)
  const blob = new Blob(['\ufeff', html], { type: 'application/msword' })
  downloadBlob(blob, filename.endsWith('.doc') ? filename : `${filename}.doc`)
}

export function downloadQuizAsHtml(quiz, filename) {
  const html = quizToHtml(quiz)
  downloadText(html, filename.endsWith('.html') ? filename : `${filename}.html`, 'text/html')
}

export function downloadQuizAsPdf(quiz, filename) {
  const html = quizToHtml(quiz)
  const win = window.open('', '_blank')
  if (win) {
    win.document.write(html)
    win.document.close()
    setTimeout(() => { win.print() }, 500)
  } else {
    downloadText(html, `${filename || 'quiz'}.html`, 'text/html')
  }
}

export function downloadFlashcardsAsDoc(data, filename) {
  const cards = (data.cards || []).map((card, index) => `
    <tr>
      <td style="padding: 14px; border: 1px solid #cbd5e1; font-weight: 800; background: #f1f5f9; width: 30%; color: #0369a1;">Card ${index + 1} Prompt</td>
      <td style="padding: 14px; border: 1px solid #cbd5e1; font-size: 1.05em; color: #0f172a;">${card.front}</td>
    </tr>
    <tr>
      <td style="padding: 14px; border: 1px solid #cbd5e1; font-weight: 800; background: #f0fdf4; color: #166534;">Answer & Explanation</td>
      <td style="padding: 14px; border: 1px solid #cbd5e1; font-size: 1em; line-height: 1.7; color: #15803d; whitespace: pre-line;">${card.back}</td>
    </tr>
  `).join('')

  const html = `<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>${data.title || 'Flashcards Master Deck'}</title>
  <style>body { font-family: Arial, sans-serif; margin: 40px; } table { width: 100%; border-collapse: collapse; margin-top: 20px; }</style>
</head>
<body>
  <div style="background: #0f766e; color: #fff; padding: 20px; border-radius: 10px;">
    <h1 style="margin: 0;">${data.title || 'Flashcards Master Deck'}</h1>
    <p style="margin: 6px 0 0 0; color: #99f6e4;">High-Yield Active Recall Study Cards</p>
  </div>
  <table>
    ${cards}
  </table>
</body>
</html>`
  const blob = new Blob(['\ufeff', html], { type: 'application/msword' })
  downloadBlob(blob, filename.endsWith('.doc') ? filename : `${filename}.doc`)
}

export function downloadFlashcardsAsPdf(data, filename) {
  const cards = (data.cards || []).map((card, index) => `
    <div style="margin-bottom: 20px; padding: 18px; background: #f8fafc; border-radius: 12px; border: 1px solid #cbd5e1; page-break-inside: avoid;">
      <p style="text-transform: uppercase; font-size: 0.75em; font-weight: 800; color: #0369a1; margin: 0 0 6px 0;">Card ${index + 1} Prompt</p>
      <h3 style="margin: 0 0 12px 0; color: #0f172a; font-size: 1.15em;">${card.front}</h3>
      <div style="padding: 12px 16px; background: #f0fdf4; border-radius: 8px; border-left: 4px solid #10b981;">
        <p style="text-transform: uppercase; font-size: 0.75em; font-weight: 800; color: #166534; margin: 0 0 4px 0;">Answer & Memory Anchor</p>
        <p style="margin: 0; color: #15803d; line-height: 1.7; font-size: 0.95em; whitespace: pre-line;">${card.back}</p>
      </div>
    </div>
  `).join('')

  const html = `<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>${data.title || 'Flashcards'}</title>
  <style>@media print { body { padding: 0; } .no-print { display: none; } } body { font-family: Inter, Arial, sans-serif; margin: 40px auto; max-width: 850px; padding: 20px; }</style>
</head>
<body>
  <div className="no-print" style="margin-bottom: 20px; text-align: right;">
    <button onclick="window.print()" style="background: #0f766e; color: #fff; border: none; padding: 10px 20px; border-radius: 8px; font-weight: bold; cursor: pointer;">🖨️ Print / Save as PDF</button>
  </div>
  <div style="background: #0f766e; color: #fff; padding: 24px; border-radius: 12px; margin-bottom: 28px;">
    <h1 style="margin: 0 0 6px 0; font-size: 2em; font-weight: 900;">${data.title || 'Flashcard Deck'}</h1>
    <p style="margin: 0; color: #99f6e4;">Total Cards: ${(data.cards || []).length}</p>
  </div>
  ${cards}
</body>
</html>`

  const win = window.open('', '_blank')
  if (win) {
    win.document.write(html)
    win.document.close()
    setTimeout(() => { win.print() }, 500)
  } else {
    downloadText(html, `${filename || 'flashcards'}.html`, 'text/html')
  }
}


