---
title: "\"If something really works it won't be published anywhere\" : r/algotrading"
source: "https://www.reddit.com/r/algotrading/comments/elva48/if_something_really_works_it_wont_be_published/"
author:
  - "[[reddit.com]]"
published: 2020-01-08
created: 2026-07-19
description:
tags:
  - "clippings"
---

- - -


- - - 

I hear this argument a lot with regards to algo-trading. To me it always sounds a lot like conspiracy theories: The belief that there are powerful organisations out there who seem to have vast knowledge and resources unlike anyone else. I am not denying that there might be organisations that have access to resources that others don't - financially, data etc., particularly in the area of low-latency trading. As long as you don't have access to the order book you just remain a 2nd (if not 3rd) class citizen.

But what I remain skeptical about is the idea that some of them are so much more advanced than the rest of the world that they can perform basically miracles. I have talked to some guys in a startup who developed the probably most sophisticated model based on whatever physics I had never seen before. Having a CS background and quite a bit of knowledge on data science as well, I was only able to grasp the fundamentals of their models. They miserably failed convincing any investment bank in the world buying into it - exactly because the investment guys did not believe into such advanced models.

Any opinions?

---

## Comments

> **\[deleted\]** · [2020-01-08](https://reddit.com/r/algotrading/comments/elva48/comment/fdkrrum/) · 74 points
> 
> I tend to agree.
> 
> Much of the edge these big firms get comes from:
> 
> 1. Capital, it takes money to make money, and more capital means more opportunities
> 2. Better order routing / Money management
> 3. Data breadth, volume and quality as well as ease of accessibility (for their employees)
> 4. A portfolio of models, not just one model to rule them all
> 5. Teams of smart people working on small portions of their stack, not a lone investor/programmer doing it all
> 
> A motivated person can find a large number of scientific articles on finance and investing which introduce state-of-the-art ideas. The infrastructure to use them appropriately is harder to build than the methods themselves. Getting clean data in an easily accessible format is often the majority of the work up front.
> 
> The easiest thing for a lone trader to do is to come up with a portfolio optimization algorithm that holds for some period longer than a week. Then you can find the data you need for cheap or free, you aren't trying to compete with the saturated HFT market, and you don't have to build a complex order system. Rebalancing can be manual to start.
> 
> Once you start trying to squeeze small amounts of profit on short timeframes it causes more problems in backtesting. I.e. would your order have filled and at what price, what are the fees, how did the tick data play out, etc. If you hold longer your returns tend to be less affected by that noise.
> 
> I personally prefer using ETFs since they are pre-diversified and you can buy some for shorts, leverage, alternative sectors, etc. However each person is different. If you know forex or options better than stocks then stick with where your domain expertise is at.
> 
> > **TBSchemer** · [2020-01-08](https://reddit.com/r/algotrading/comments/elva48/comment/fdlm2e4/) · 22 points
> > 
> > Thank you, this is exactly the philosophy I've been operating on, and it feels good to have someone else confirm it.
> > 
> > I don't plan on competing with the big guys by daytrading. But swing-trading? There are certainly opportunities there, that can be captured by anyone with some aptitude in programming and statistics, as well as a bit of creativity in searching for data.

> **FX-Macrome** · [2020-01-08](https://reddit.com/r/algotrading/comments/elva48/comment/fdkn1le/) · 99 points
> 
> Sophisticated does not mean good. I’ve said this before, many firms still use linear regression because it works. I believe most, if not all (except bleeding edge of tech), techniques are public knowledge.
> 
> The secret sauce is what combination of these techniques will work? With what data? With what instruments? Risk management? Time horizon? Etc.
> 
> > **killerguppy101** · [2020-01-08](https://reddit.com/r/algotrading/comments/elva48/comment/fdl3zym/) · 22 points
> > 
> > Agreed. Ideas are a dime a dozen. Implementation is what separates winners and losers, in just about any industry.
> > 
> > **\_\_deandre** · [2020-01-08](https://reddit.com/r/algotrading/comments/elva48/comment/fdl5k28/) · 12 points
> > 
> > Can you give examples (general idea) on how/where (use cases) those firms use linear regression?
> > 
> > **unfair\_bastard** · [2020-01-09](https://reddit.com/r/algotrading/comments/elva48/comment/fdmkhfq/) · 12 points
> > 
> > ^THIS
> > 
> > most of this entire thread is missing the point of what "if something really works it wont be published" really means
> > 
> > the "something" really working, is the entire arrangement: models, software, hardware, order routing, institutional relationships
> > 
> > a better way to describe it would be
> > 
> > "no sane market participant will tell you the entirety of where their edge comes from"
> > 
> > **\[deleted\]** · [2020-01-08](https://reddit.com/r/algotrading/comments/elva48/comment/fdkz7q8/) · 15 points
> > 
> > Yep. It's not the underlying algo components so much as the proportions, constants and coefficients that are the secret sauce.
> > 
> > > **eoliveri** · [2020-01-08](https://reddit.com/r/algotrading/comments/elva48/comment/fdl80ho/) · 12 points
> > > 
> > > In fact, some research indicates that not even the weights in a linear model are as important as getting the right variables and signs:
> > > 
> > > [https://psycnet.apa.org/record/1979-30170-001](https://psycnet.apa.org/record/1979-30170-001)

> **Nater5000** · [2020-01-08](https://reddit.com/r/algotrading/comments/elva48/comment/fdl14kg/) · 20 points
> 
> > But what I remain skeptical about is the idea that some of them are so much more advanced than the rest of the world that they can perform basically miracles.
> 
> I don't know about "miracles," but science looks a lot like magic until you understand it. It's not that they have some secret algorithm that can print money, but rather system which can consistently produce value. These systems are non-static and are comprised of everything from complex mathematics to basic human common sense.
> 
> Put it another way: it's quite easy for me or you to imagine flying to the moon. We could be experts in physics and engineering, and we even know it's possible since we know it's been done before. Yet the idea of me or you building a space ship and landing on the moon sounds absolutely preposterous, not because the task is impossible, but because it takes a lot of people and a lot of resources to make something like that happen.
> 
> From the outside, it might seem like institutional trading is just a scaled up version of something someone can put together on their own, but that would be like building a successful model rocket and assuming flying to the moon is just a scaled up version of that. Like, in essence, it kind of is, but in practice they are basically completely different challenges.

> **Tacoslim** · [2020-01-08](https://reddit.com/r/algotrading/comments/elva48/comment/fdkxbyb/) · 19 points
> 
> All the information is out there but it’s not in a simple 10 page research article or on a blog post that a comp sci student can spin up over a couple of weekends and make fast reliable money.
> 
> I think a lot of people get into algo trading with the expectation that they’ll be able to find and replicate profitable strategies and this is where the “research articles are a waste of time” comes from.

> **Paul5By5** · [2020-01-08](https://reddit.com/r/algotrading/comments/elva48/comment/fdl5bb1/) · 18 points
> 
> Watch that Jim Simons speech when someone asks if he would offer up a clue about his algorithms. His answer was 'No.'
> 
> Lol

> **Beliavsky** · [2020-01-08](https://reddit.com/r/algotrading/comments/elva48/comment/fdkgx7u/) · 15 points
> 
> "They miserably failed convincing any investment bank in the world buying into it - exactly because the investment guys did not believe into such advanced models. "
> 
> Did they have live trading results, even with a small capital base?
> 
> I think that good strategies such as "buy value stocks" or "buy FX carry" will be published but that very high Sharpe ratio strategies usually will not be. OTOH, the profit many academics are after is tenure at a good university, or a job or consulting arrangement at a hedge fund like AQR, and revealing things that lead to jobs and promotions may be rational for them.

> **PitifulNose** · [2020-01-08](https://reddit.com/r/algotrading/comments/elva48/comment/fdl7i0s/) · 11 points
> 
> There are both cases where:
> 
> 1. Things that really work are published and commonly known: As an example the primary drivers of alpha for market making / high frequency trading comes from correlation between 2 or more instruments, exchanges, indexes, etc. The logic that HF teams use is very well known, but their speed to be first is more what gives them the advantage. It's less about a secret sauce.
> 2. Things that work well can be very complex also. I know a guy who runs a hedge fund that uses one of the largest ML / AI data-sets in the industry. There was a point early on where he and his team had to prove their merit to get investor money initially. So they build everything with their own gear and actually did quite well on their own before they reached out to investors to scale. In some cases it helps to have a proven use case and track record before you seek investment.
> 
> And on the topic of publishing things that work. You can find plenty of law suits related to trading where strategies were revealed in extreme detail. Most of these worked to an extent legally, but there may have been something adjacent to the algo that triggered the law suit. There are a few good ones on the HF sub. Also I have shared a few edges before. I am not a pro by any means (no non-disclosure agreements pending). But the point is that there are some things out there that meets this criteria.
> 
> But I would say for every 1 legit thing you might find, there will be 99 snake oil salesmen selling spaghetti charts with magic indicators.
> 
> > **daermonn** · [2020-01-09](https://reddit.com/r/algotrading/comments/elva48/comment/fdluwi0/) · 5 points
> > 
> > > You can find plenty of law suits related to trading where strategies were revealed in extreme detail. Most of these worked to an extent legally, but there may have been something adjacent to the algo that triggered the law suit. There are a few good ones on the HF sub. Also I have shared a few edges before. I am not a pro by any means (no non-disclosure agreements pending).
> > 
> > Do you mind linking to these again? I wasn't aware there was a hft sub here, and I can't seem to find it. Would love to see the detail here. To what extent to hft strategies work are lower frequency?

> **FieldLine** · [2020-01-09](https://reddit.com/r/algotrading/comments/elva48/comment/fdlnwgj/) · 8 points
> 
> > They miserably failed convincing any investment bank in the world buying into it - exactly because the investment guys did not believe into such advanced models.
> 
> More likely because it hasn't been proven to work.
> 
> I've developed models that worked great on past data. They then failed miserably when actually put to the test. I don't believe for a second that Wall Street passed up on a model that has a track record of success.

> **istavnit** · [2020-01-09](https://reddit.com/r/algotrading/comments/elva48/comment/fdmgygv/) · 8 points
> 
> Not a conspiracy theory. Simons is tight-lipped.
> 
> I - personally have taken down a number of posts I made here because I concluded I was revealing too much.
> 
> Speculation is a 0 sum game.

> **\[deleted\]** · [2020-01-08](https://reddit.com/r/algotrading/comments/elva48/comment/fdkx7cq/) · 7 points
> 
> It's the hedge fund culture. You should check out information wrt to the non-competes you have to sign. Furthermore, read about how DE Shaw treats their former PMs.

> **UL\_Paper** · [2020-01-08](https://reddit.com/r/algotrading/comments/elva48/comment/fdkxj1u/) · 12 points
> 
> Checks out. You will be punished for publishing something that works, as others will join in with capital which will eliminate the alpha.

> **cakeofzerg** · [2020-01-08](https://reddit.com/r/algotrading/comments/elva48/comment/fdl01iu/) · 6 points
> 
> To trade a model in all climates you have to understand it in detail, so no firm will buy some extremely complex model they don't have the ability to fully understand.
> 
> The well financed firms use many kinds of mostly simple data which is then evaluated using moderately complex models.
> 
> The average firm uses a few select kinds of simple but powerful data and simple buy powerful models. You can still beat the market in this way.

> **Arbitrage84** · [2020-01-08](https://reddit.com/r/algotrading/comments/elva48/comment/fdlkhk0/) · 6 points
> 
> There are thousands of academic researchers looking for factors. There are thousands of industry researchers looking for factors. Any edge found must also scale otherwise acting on the signal closes the signals edge. Incentives exist to keep discoveries off the public domain.

> **linearanalyst** · [2020-01-09](https://reddit.com/r/algotrading/comments/elva48/comment/fdm040d/) · 5 points
> 
> I am one of those who say that. What I mean is you can't find something that works out of one paper or research. Even combining two methods may generate alpha. For example, price action and options data are two publicly available sources with extensive research papers on each.

> **PLxFTW** · [2020-01-08](https://reddit.com/r/algotrading/comments/elva48/comment/fdkyr4t/) · 8 points
> 
> One of my professors and a friend of his who have both worked in industry told me that there are still many firms that operate completely within excel and their techniques are basic, such as linear regression, etc.
> 
> However, he also said a lot of people don’t have any clue what their doing and misunderstand even basic statistics and thus their models are useless.

> **\[deleted\]** · [2020-01-09](https://reddit.com/r/algotrading/comments/elva48/comment/fdmldea/) · 3 points
> 
> A few thoughts:
> 
> 1. Most investment organizations use fairly basic theory. Their advantage comes up from other areas.
> 2. There are tons of published papers on financial models for the stock market. There is valuable information in those papers.
> 3. There are a few unicorn companies that are head and shoulders above the others in terms of theory and technology. But the theory and technology they work is probably not that different than what you see published in academic journals and is available in open source libraries. They're just better at deciding what to use and how to apply it.
> 4. Most investment banks aren't going to take on the risk of putting a lot of money into some model from an unknown startup. They're going to stick to safer ways of making money. That doesn't mean their model doesn't have value.

> **AdamCantor** · [2020-01-09](https://reddit.com/r/algotrading/comments/elva48/comment/fdmz8q4/) · 2 points
> 
> this is true that strategies and systems that work are not given away in the masses,either for free or for a price. however the ones that do work and are passed on are always short lived in their advertisement. its all about trying and testng and taking the risk i guess

> **yachiro1** · [2020-01-09](https://reddit.com/r/algotrading/comments/elva48/comment/fdn39en/) · 2 points
> 
> The only two parameters you need to blend is time and liquidity zones..no need for sophisticated data and algos. so for a short answer: no..there is stuffs that works and it's published.