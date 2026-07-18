---
title: "Tools, libraries, and frameworks for quant research at a HFT firm"
source: "https://hftgirl.medium.com/tools-libraries-and-frameworks-for-quant-research-at-a-hft-firm-bf0536f0717b"
author:
  - "[[medium.com]]"
published: 2023-05-04
created: 2026-07-19
description: "I get asked very often what tools I use as a quant researcher at a HFT firm."
tags:
  - "clippings"
---

- - -


- - - 

I get asked very often what tools I use as a quant researcher at a HFT firm.

I’ve worked at two of the largest market makers in the world. My responsibility was to manage a team of researchers and dedicated engineers for my team, but I also worked with core developers and network engineers who supported everyone.

At both companies, we didn’t like external dependencies because they’d be hard to maintain and could potentially break your production trading or the BOD or EOD workflows that supported your production trading. The stack resembled a HPC or bioinformatics environment; the total data amounted to tens of petabytes; the typical job processed hundreds of GB to several TB per day, and my jobs usually numbered in the thousands to millions per day.

My preferred languages for research work are **C++** and **Python**. There’s nothing particularly fanciful about the tools I go to in both languages because we usually have inhouse libraries and CLIs for everything.

This concern becomes more obvious when you’re pushing the boundaries of hardware and tools that people take for granted to work. My team fixed bugs and performance issues in the kernel; Clang; Boost, and popular build tools like Cmake and Bazel. If you’re reading this post, you’ve probably been a beneficiary of code I’ve written.

With that said, there’s more to write about things that I like outside of the critical path.

## 1\. Command-line environment

My preferred editor is **vim** because it’s widely available on Linux boxes. Some utilities that I find myself reaching for frequently are **tcpdump, rsync, ip**, **ifconfig**, **route, cset, lldb**, **valgrind**, **strace**, **grep**, and **ag**.

## 2\. Data exploration

For datasets that fit well within the memory available on a single large server, the typical data science stack of an **IPython notebook**, **numpy**, **pandas**, **matplotlib**, and **sklearn** is my preference. I have these in my default IPython profile.

## Get Cara’s stories in your inbox

Join Medium for free to get updates from this writer.

I occasionally also find myself reaching into **cxopt**, **cplex**, and **scipy.optimize** for simpler optimization routines; **statsmodels** for time series models; **keras** as a TensorFlow interface, among many others.

Sometimes, I have to keep intermediate datasets like design matrices. I usually use **h5py** or **pyarrow.parquet** for these.

I occasionally find it easier to script in R. I love using **ggplot2** for graphing. I usually have a sysadmin spin up a **RStudio** server to keep around.

My strategies usually took thousands of compute hours for optimization each day. A good job scheduler for running batch jobs on the cluster is a must. I’ve used a few flavors of these, including **Slurm** and **SGE**. Some companies use Dask or other flavors of distributed computing tools for exploration of larger datasets, but I rather write them as a batch job if it gets to that size.

There are always three custom GUIs that I make sure to write to facilitate data exploration. One is a tool to plot and **visualize order book data**; another is tool for **inspecting market data messages at the packet level**, and finally there’s one that will model, trade, and order logs for **post-trade analysis**. There’s no adequate open source or commercial solution for these, and these are invoked so frequently that it’s important that they’re fast. If the company doesn’t have such a tool on hand, I usually write one in C++ and **Qt**.

## 3\. Storage

I usually work in an environment that has a mix of **pcaps** for raw data and **binary flat files**,and some horizontally-scalable database for normalized data. These files are usually stored on storage systems that are easy to manage or scale for performance. At one firm, we had a large amount of **ZFS** storage that was complemented by **Lustre** as a high-performance scratch space for our batch jobs. Besides this, I’ve used **EMC Isilon** and **Qumulo**.

When working with large amounts of data, it’s essential to minimize network file I/O by performing computations at the source. Some companies opt for **Spark** or **Hadoop** for this purpose, I prefer to store at least some of the normalized data in a column-oriented DBMS like **kdb** or **Vertica**. With these, it’s easy to run queries that shrink the working set before it’s read by a Python or C++ client for further manipulation and modeling.

## 4\. ETL

I don’t have a preferred flavor of ETL scheduler, but it’s a necessity. At one place, we used **Jenkins** and cronjobs for our ETL pipelines and had thousands of Jenkins builds corresponding to these pipelines. I’ve also tried **Airflow**, **Buildkite**, **Prefect**, and **Luigi** for this. Each of them has its quirks, and not one is obviously better than the others.