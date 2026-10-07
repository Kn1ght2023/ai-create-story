import { writable } from 'svelte/store';

export const currentPage = writable(window.location.hash.slice(1) || 'config');

window.addEventListener('hashchange', () => {
  currentPage.set(window.location.hash.slice(1) || 'config');
});

export function navigate(page) {
  window.location.hash = '#' + page;
}
