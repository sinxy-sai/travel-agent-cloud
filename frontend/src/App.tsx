import { useMemo, useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { Button, Input, InputNumber, Select, Spin } from 'antd';
import { SendOutlined } from '@ant-design/icons';
import { createTripPlan, type TripPlanResponse } from './lib/api';

const interestOptions = [
  'city walk',
  'local food',
  'museums',
  'nature',
  'family friendly',
  'photography',
  'slow travel',
];

export default function App() {
  const [destination, setDestination] = useState('Chengdu');
  const [days, setDays] = useState(3);
  const [budget, setBudget] = useState('moderate');
  const [interests, setInterests] = useState<string[]>(['local food', 'city walk']);
  const [plan, setPlan] = useState<TripPlanResponse | null>(null);

  const mutation = useMutation({
    mutationFn: createTripPlan,
    onSuccess: setPlan,
  });

  const requestPreview = useMemo(
    () => `${days} days in ${destination}, ${budget} budget, focused on ${interests.join(', ')}`,
    [budget, days, destination, interests],
  );

  return (
    <main className="min-h-screen bg-mist">
      <section className="mx-auto grid min-h-screen max-w-7xl grid-cols-1 gap-6 px-5 py-6 lg:grid-cols-[360px_1fr]">
        <aside className="rounded-lg bg-white p-5 shadow-panel">
          <div className="mb-6">
            <p className="text-sm font-medium uppercase tracking-wide text-trail">Travel Agent Cloud</p>
            <h1 className="mt-2 text-3xl font-semibold text-ink">Trip planner workspace</h1>
          </div>

          <div className="space-y-4">
            <label className="block">
              <span className="mb-2 block text-sm font-medium text-ink">Destination</span>
              <Input value={destination} onChange={(event) => setDestination(event.target.value)} />
            </label>

            <label className="block">
              <span className="mb-2 block text-sm font-medium text-ink">Days</span>
              <InputNumber min={1} max={14} value={days} onChange={(value) => setDays(value ?? 1)} className="w-full" />
            </label>

            <label className="block">
              <span className="mb-2 block text-sm font-medium text-ink">Budget</span>
              <Select
                value={budget}
                onChange={setBudget}
                className="w-full"
                options={[
                  { value: 'low', label: 'Low' },
                  { value: 'moderate', label: 'Moderate' },
                  { value: 'premium', label: 'Premium' },
                ]}
              />
            </label>

            <label className="block">
              <span className="mb-2 block text-sm font-medium text-ink">Interests</span>
              <Select
                mode="multiple"
                value={interests}
                onChange={setInterests}
                className="w-full"
                options={interestOptions.map((value) => ({ value, label: value }))}
              />
            </label>

            <Button
              type="primary"
              icon={<SendOutlined />}
              loading={mutation.isPending}
              onClick={() =>
                mutation.mutate({
                  destination,
                  days,
                  budget,
                  interests: interests.join(', '),
                })
              }
              className="w-full"
            >
              Generate itinerary
            </Button>
          </div>
        </aside>

        <section className="rounded-lg bg-white p-5 shadow-panel">
          <div className="mb-5 border-b border-slate-200 pb-4">
            <p className="text-sm text-slate-500">Current request</p>
            <h2 className="mt-1 text-xl font-semibold text-ink">{requestPreview}</h2>
          </div>

          {mutation.isPending && (
            <div className="flex h-80 items-center justify-center">
              <Spin tip="Planning route..." />
            </div>
          )}

          {mutation.isError && (
            <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-red-700">
              Agent runtime is unavailable. Start the FastAPI service and try again.
            </div>
          )}

          {!mutation.isPending && !plan && !mutation.isError && (
            <div className="rounded-lg border border-dashed border-slate-300 p-8 text-slate-600">
              Generate a plan to preview the first Agent Runtime response.
            </div>
          )}

          {plan && !mutation.isPending && (
            <div>
              <div className="mb-5">
                <h2 className="text-2xl font-semibold text-ink">{plan.title}</h2>
                <p className="mt-2 max-w-3xl text-slate-600">{plan.summary}</p>
              </div>

              <div className="grid gap-4">
                {plan.days.map((day) => (
                  <article key={day.day} className="rounded-lg border border-slate-200 p-4">
                    <div className="mb-3 flex items-center justify-between">
                      <h3 className="text-lg font-semibold text-ink">Day {day.day}</h3>
                      <span className="rounded-full bg-trail px-3 py-1 text-sm text-white">{day.theme}</span>
                    </div>
                    <div className="grid gap-3 md:grid-cols-3">
                      <PlanBlock title="Morning" value={day.morning} />
                      <PlanBlock title="Afternoon" value={day.afternoon} />
                      <PlanBlock title="Evening" value={day.evening} />
                    </div>
                  </article>
                ))}
              </div>

              <div className="mt-5 rounded-lg bg-slate-50 p-4">
                <h3 className="font-semibold text-ink">Travel notes</h3>
                <ul className="mt-2 list-inside list-disc text-slate-600">
                  {plan.tips.map((tip) => (
                    <li key={tip}>{tip}</li>
                  ))}
                </ul>
              </div>
            </div>
          )}
        </section>
      </section>
    </main>
  );
}

function PlanBlock({ title, value }: { title: string; value: string }) {
  return (
    <div className="rounded-md bg-mist p-3">
      <p className="text-sm font-medium text-trail">{title}</p>
      <p className="mt-1 text-sm leading-6 text-slate-700">{value}</p>
    </div>
  );
}
