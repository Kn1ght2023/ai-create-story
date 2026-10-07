<script>
  import { onDestroy } from 'svelte';
  import { taskTokenUsage } from '../lib/stores.js';
  import { TOKEN_POLL_INTERVAL_MS } from '../lib/tokenPoll.js';
  import { t } from '../lib/i18n/index.js';

  export let className = 'badge badge-xs badge-info gap-1 font-mono';

  let displayPrompt = 0;
  let displayCompletion = 0;
  let rafId = null;
  /** @type {{ start: number, fromP: number, fromC: number, toP: number, toC: number } | null} */
  let anim = null;

  function stopAnim() {
    if (rafId != null) {
      cancelAnimationFrame(rafId);
      rafId = null;
    }
    anim = null;
  }

  function tick(now) {
    if (!anim) return;
    const t = Math.min(1, (now - anim.start) / TOKEN_POLL_INTERVAL_MS);
    displayPrompt = Math.round(anim.fromP + (anim.toP - anim.fromP) * t);
    displayCompletion = Math.round(anim.fromC + (anim.toC - anim.fromC) * t);
    if (t < 1) {
      rafId = requestAnimationFrame(tick);
    } else {
      rafId = null;
      anim = null;
    }
  }

  function startAnim(toP, toC) {
    stopAnim();
    let fromP = displayPrompt;
    let fromC = displayCompletion;
    if (toP < displayPrompt) {
      displayPrompt = 0;
      fromP = 0;
    }
    if (toC < displayCompletion) {
      displayCompletion = 0;
      fromC = 0;
    }
    anim = {
      start: performance.now(),
      fromP,
      fromC,
      toP,
      toC,
    };
    rafId = requestAnimationFrame(tick);
  }

  const unsub = taskTokenUsage.subscribe(v => {
    if (v) {
      startAnim(v.prompt_tokens, v.completion_tokens);
    } else {
      stopAnim();
      displayPrompt = 0;
      displayCompletion = 0;
    }
  });

  onDestroy(() => {
    unsub();
    stopAnim();
  });
</script>

{#if $taskTokenUsage}
  <span class={className}>
    {$t('task.tokens.usage', {
      prompt: displayPrompt.toLocaleString(),
      completion: displayCompletion.toLocaleString(),
    })}
  </span>
{/if}
