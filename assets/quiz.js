// Shared quiz widget. Markup contract:
// <div class="quiz">
//   <div class="q" data-answer="1">
//     <p class="stem">Question?</p>
//     <button class="opt">Option 0</button>
//     <button class="opt">Option 1</button>
//     <div class="explain">Why option 1 is right.</div>
//   </div>
// </div>
// data-answer is the zero-based index of the correct option. One attempt per
// question: after the first click the correct option is revealed and the
// explanation shown, so the feedback loop is immediate.
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.quiz .q').forEach((q) => {
    const answer = Number(q.dataset.answer);
    const opts = Array.from(q.querySelectorAll('button.opt'));
    opts.forEach((btn, i) => {
      btn.addEventListener('click', () => {
        if (q.classList.contains('answered')) return;
        q.classList.add('answered');
        btn.classList.add(i === answer ? 'correct' : 'wrong');
        if (i !== answer) opts[answer].classList.add('correct');
        opts.forEach((b) => (b.disabled = true));
      });
    });
  });
});
