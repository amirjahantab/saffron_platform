const form = document.getElementById('assistant-form');
if (form) {
  form.addEventListener('submit', async event => {
    event.preventDefault();
    const output = document.getElementById('assistant-results');
    const button = form.querySelector('button[type=submit]');
    button.disabled = true;
    const container = document.createElement('div');
    container.className = 'assistant-result';
    container.textContent = 'در حال بررسی پرسش شما…';
    output.replaceChildren(container);
    try {
      const response = await fetch(form.action, {
        method: 'POST', credentials: 'same-origin', headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': form.querySelector('[name=csrfmiddlewaretoken]').value,
        },
        body: JSON.stringify({message: form.querySelector('textarea').value}),
        signal: AbortSignal.timeout(18000),
      });
      const data = await response.json();
      container.textContent = data.message || 'پاسخ دریافت نشد؛ لطفاً دوباره تلاش کنید.';
      const safeLink = (url, label, css) => {
        const destination = new URL(url, location.origin);
        if (destination.origin !== location.origin) return null;
        const link = document.createElement('a');
        link.href = destination.href;
        link.textContent = label;
        link.className = css;
        container.append(link);
        return link;
      };
      for (const product of data.products || []) {
        const link = safeLink(product.url, product.name, 'assistant-product');
        if (!link) continue;
        const details = document.createElement('small');
        details.textContent = `${product.weight} · ${product.origin} · ${product.price || 'بدون قیمت فعال'} · ${product.available ? 'موجود' : 'ناموجود'}`;
        link.append(document.createElement('br'), details);
      }
      for (const [key, label] of [['support_url', 'گفتگو با پشتیبانی'], ['order_url', 'جزئیات سفارش'], ['policy_url', 'مشاهده متن کامل']]) {
        if (data[key]) safeLink(data[key], label, 'text-link mt-5');
      }
    } catch {
      container.textContent = 'ارتباط برقرار نشد. لطفاً دوباره تلاش کنید یا از بخش پشتیبانی پیام بفرستید.';
    } finally {
      button.disabled = false;
    }
  });
}

const responsiveFilters = document.querySelector('[data-responsive-filter]');
if (responsiveFilters) responsiveFilters.open = matchMedia('(min-width: 761px)').matches;
