import { beforeEach, expect, it } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import SupportPanel from '../components/SupportPanel.svelte';
import { supportRequests, supportTaskId } from '../store';

beforeEach(() => { supportTaskId.set('task'); supportRequests.set([]); });

it('does not label an unknown support state closed', () => {
  supportRequests.set([{support_id:'s1', status:'unknown', blocks_resume:true}]);
  render(SupportPanel);
  expect(screen.getByTestId('support-card').textContent).toContain('DURUM BİLİNMİYOR');
  expect(screen.getByTestId('support-card').textContent).not.toContain('KAPANDI');
});
